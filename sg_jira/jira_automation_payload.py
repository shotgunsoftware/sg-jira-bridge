# Copyright 2026 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

"""
Normalize Jira Project Automation web-request bodies into webhook-shaped events.

Site webhooks include a native ``changelog`` block; Project Automation does not
expose ``{{#changelog.changedFields}}``. For field rules, send ``field_change``
with ``{{fieldChange.fromString}}`` / ``{{fieldChange.toString}}`` — see
:doc:`jira_automation`.

Issue automation is inferred from the body: ``field_change`` / ``changed_fields``
for partial sync, otherwise full Issue sync. Comment/worklog rules still use
``trigger``. See :doc:`jira_automation`.
"""

import re

from sg_jira.constants import (
    JIRA_PROJECT_AUTOMATION_SOURCE,
    JIRA_SYNC_IN_FPTR_FIELD,
)

# Comment/worklog automation: one Jira rule → one trigger value.
TRIGGER_TO_WEBHOOK_EVENT = {
    "comment.added": "comment_created",
    "comment.edited": "comment_updated",
    "comment.deleted": "comment_deleted",
    "worklog.added": "worklog_created",
    "worklog.updated": "worklog_updated",
    "worklog.deleted": "worklog_deleted",
}

_ISSUE_WEBHOOK_EVENTS = frozenset(
    {
        "jira:issue_updated",
        "jira:issue_created",
    }
)

_ENTITY_WEBHOOK_EVENTS = frozenset(
    {
        "comment_created",
        "comment_updated",
        "comment_deleted",
        "worklog_created",
        "worklog_updated",
        "worklog_deleted",
    }
)

_SUPPORTED_WEBHOOK_EVENTS = _ISSUE_WEBHOOK_EVENTS | _ENTITY_WEBHOOK_EVENTS

# Deprecated ``webhook_event`` on comment/worklog bodies → ``trigger`` (inference).
_LEGACY_WEBHOOK_EVENT_TO_TRIGGER = {
    "comment_created": "comment.added",
    "comment_updated": "comment.edited",
    "comment_deleted": "comment.deleted",
    "worklog_created": "worklog.added",
    "worklog_updated": "worklog.updated",
    "worklog_deleted": "worklog.deleted",
}

# Smart values left unexpanded in the rule body look like this in audit logs.
_UNEXPANDED_SMART_VALUE_RE = (
    r"^\{\{(fieldChange|initiator|issue|changelog|comment|worklog)(\.|\}\})"
)


class JiraAutomationPayloadError(ValueError):
    """Raised when a Jira Project Automation request body is invalid."""


def normalize_automation_request(payload, resource_type, resource_id, jira=None):
    """
    Convert a Project Automation POST body into an event the Generic Syncer accepts.

    Payloads without ``source: jira_project_automation`` are returned unchanged.
    Real Jira webhooks are unaffected.

    :param dict payload: Parsed JSON request body.
    :param str resource_type: Jira resource type from the URL path (e.g. ``issue``).
    :param str resource_id: Jira Issue key from the URL path.
    :param jira: Optional :class:`~sg_jira.jira_session.JiraSession` for
        Issue id resolution, and comment/worklog loads.
    :returns: Event dictionary in Jira webhook shape.
    :raises JiraAutomationPayloadError: On invalid automation input.
    """
    if not isinstance(payload, dict):
        raise JiraAutomationPayloadError("Request body must be a JSON object.")

    event = dict(payload)

    if event.get("source") != JIRA_PROJECT_AUTOMATION_SOURCE:
        return event

    if not resource_type or resource_type.lower() != "issue":
        raise JiraAutomationPayloadError(
            "Jira Project Automation only supports Issue resources in the URL path."
        )

    if not resource_id or not isinstance(resource_id, str):
        raise JiraAutomationPayloadError(
            "The request path must include a Jira Issue key."
        )

    trigger = event.pop("trigger", None)
    webhook_event = event.pop("webhook_event", None) or event.pop("webhookEvent", None)
    if trigger is None and webhook_event:
        trigger = _LEGACY_WEBHOOK_EVENT_TO_TRIGGER.get(webhook_event)
        if trigger is not None:
            webhook_event = None
    trigger = _infer_trigger_if_missing(event, trigger)
    webhook_event, _trigger = _resolve_trigger_and_webhook_event(
        trigger, webhook_event, event
    )

    user = _pop_actor(event)

    event.pop("source", None)

    issue_ref = _issue_reference(resource_id, jira)

    if webhook_event in _ENTITY_WEBHOOK_EVENTS:
        normalized = _normalize_entity_automation(
            webhook_event, issue_ref, event, resource_id, jira
        )
    else:
        normalized = _normalize_issue_automation(
            webhook_event, issue_ref, event, resource_id, jira
        )

    if user is not None:
        normalized["user"] = user

    return normalized


def _infer_trigger_if_missing(event, trigger):
    """
    Infer comment/worklog triggers from entity ids when missing.

    Issue create/update/field sync is inferred from ``field_change`` presence,
    not from ``trigger``.
    """
    if trigger is not None:
        return trigger
    if event.get("comment_id") is not None or event.get("comment") is not None:
        raise JiraAutomationPayloadError(
            "Comment rules require trigger: comment.added, comment.edited, or "
            "comment.deleted (same as your Jira automation trigger)."
        )
    if event.get("worklog_id") is not None or event.get("worklog") is not None:
        raise JiraAutomationPayloadError(
            "Worklog rules require trigger: worklog.added, worklog.updated, or "
            "worklog.deleted (same as your Jira automation trigger)."
        )
    return None


def _resolve_trigger_and_webhook_event(trigger, webhook_event, event):
    if trigger is not None:
        if trigger not in TRIGGER_TO_WEBHOOK_EVENT:
            raise JiraAutomationPayloadError(
                f"Unsupported trigger {trigger!r}. "
                f"Issue sync uses field_change or a minimal body (no trigger). "
                f"Comment/worklog triggers: "
                f"{', '.join(sorted(TRIGGER_TO_WEBHOOK_EVENT.keys()))}."
            )
        mapped = TRIGGER_TO_WEBHOOK_EVENT[trigger]
        if webhook_event and webhook_event != mapped:
            raise JiraAutomationPayloadError(
                f"trigger {trigger!r} maps to {mapped!r}, but webhook_event "
                f"was {webhook_event!r}. Use trigger only."
            )
        return mapped, trigger

    if webhook_event:
        if webhook_event not in _SUPPORTED_WEBHOOK_EVENTS:
            raise JiraAutomationPayloadError(
                f"Unsupported webhook_event {webhook_event!r}. "
                f"See docs/jira_automation.rst."
            )
        return webhook_event, None

    return "jira:issue_updated", None


def _pop_actor(event):
    """Return the initiator as ``user`` for loop detection (actor preferred)."""
    actor = event.pop("actor", None)
    user = event.pop("user", None)
    initiator = actor if actor is not None else user
    if initiator is not None and not isinstance(initiator, dict):
        raise JiraAutomationPayloadError("actor must be an object.")
    return initiator


def _issue_reference(resource_id, jira):
    issue_ref = {"key": resource_id}
    if jira is not None:
        try:
            jira_issue = jira.issue(resource_id)
            issue_ref["id"] = str(jira_issue.id)
        except Exception as e:
            raise JiraAutomationPayloadError(
                f"Unable to load Jira Issue {resource_id!r}."
            ) from e
    return issue_ref


def _normalize_entity_automation(webhook_event, issue_ref, event, issue_key, jira):
    entity_kind, _action = webhook_event.split("_", 1)

    for key in ("field_change", "changed_fields"):
        if key in event:
            raise JiraAutomationPayloadError(
                f"{key} applies to Issue field rules only, not {webhook_event}."
            )

    inline_entity = event.pop(entity_kind, None)
    entity_id = event.pop(f"{entity_kind}_id", None)
    entity_id = _coalesce_entity_id(entity_kind, inline_entity, entity_id)

    if event:
        raise JiraAutomationPayloadError(
            f"Unexpected keys in automation body: {', '.join(sorted(event.keys()))}."
        )

    entity = _resolve_comment_or_worklog_entity(
        entity_kind, _action, inline_entity, entity_id, issue_key, jira
    )

    return {
        "webhookEvent": webhook_event,
        "issue": issue_ref,
        entity_kind: entity,
    }


def _coalesce_entity_id(entity_kind, inline_entity, entity_id):
    """Accept ``comment_id`` / ``\"{{comment.id}}\"`` or ``\"comment\": \"{{comment.id}}\"``."""
    if entity_id is not None:
        return entity_id
    if isinstance(inline_entity, str):
        return inline_entity.strip()
    if isinstance(inline_entity, (int, float)):
        return str(int(inline_entity))
    if isinstance(inline_entity, dict) and inline_entity.get("id") is not None:
        return inline_entity.get("id")
    return None


def _resolve_comment_or_worklog_entity(
    entity_kind, action, inline_entity, entity_id, issue_key, jira
):
    entity = None
    if inline_entity is not None and isinstance(inline_entity, dict):
        entity = dict(inline_entity)

    if entity_id is not None:
        entity_id = str(entity_id).strip()
        if _looks_like_unexpanded_smart_value(entity_id):
            raise JiraAutomationPayloadError(
                f"{entity_kind}_id contains an unexpanded Jira smart value."
            )
        if entity is None:
            entity = {"id": entity_id}
        elif not entity.get("id"):
            entity["id"] = entity_id

    if not entity or not entity.get("id"):
        raise JiraAutomationPayloadError(
            f'Paste "{entity_kind}_id": "{{{{{entity_kind}.id}}}}" in Custom data '
            f"(Jira fills in the id when the rule runs — you never type a number)."
        )

    entity["id"] = str(entity["id"])

    if action == "deleted":
        if entity_kind == "worklog" and "issueId" not in entity:
            entity["issueId"] = issue_key
        return entity

    if _entity_needs_jira_fetch(entity, action):
        if jira is None:
            raise JiraAutomationPayloadError(
                f"{entity_kind}_id requires a Jira connection to load {entity_kind} data."
            )
        try:
            if entity_kind == "comment":
                entity = jira.comment_as_webhook_entity(issue_key, entity["id"])
            else:
                entity = jira.worklog_as_webhook_entity(issue_key, entity["id"])
        except ValueError as e:
            raise JiraAutomationPayloadError(str(e)) from e

    return entity


def _entity_needs_jira_fetch(entity, action):
    if action == "created":
        author = entity.get("author") or {}
        return not (author.get("accountId") or author.get("name"))
    if action == "updated":
        author = entity.get("updateAuthor") or entity.get("author") or {}
        return not (author.get("accountId") or author.get("name"))
    return False


def _normalize_issue_automation(webhook_event, issue_ref, event, resource_id, jira):
    if event.pop("sync_changed_only", False):
        raise JiraAutomationPayloadError(
            "sync_changed_only is not supported. Use field_change with "
            "{{fieldChange.fromString}} and {{fieldChange.toString}}."
        )

    field_change = event.pop("field_change", None)
    changed_fields = event.pop("changed_fields", None)
    partial_sync = field_change is not None or changed_fields is not None

    if field_change is not None and changed_fields is not None:
        raise JiraAutomationPayloadError(
            "Use either field_change or changed_fields, not both."
        )

    if event:
        raise JiraAutomationPayloadError(
            f"Unexpected keys in automation body: {', '.join(sorted(event.keys()))}."
        )

    normalized = {
        "webhookEvent": webhook_event,
        "issue": issue_ref,
    }

    if field_change is not None:
        normalized["changelog"] = {
            "items": [
                _field_spec_to_changelog_item(
                    field_change, jira, require_value_strings=partial_sync
                )
            ],
        }
        return normalized

    if changed_fields is not None:
        if not isinstance(changed_fields, list) or not changed_fields:
            raise JiraAutomationPayloadError(
                "changed_fields must be a non-empty array."
            )
        normalized["changelog"] = {
            "items": [
                _field_spec_to_changelog_item(
                    entry, jira, require_value_strings=partial_sync
                )
                for entry in changed_fields
            ],
        }
        return normalized

    normalized["changelog"] = _automation_full_sync_changelog(jira)
    return normalized


def _automation_full_sync_changelog(jira):
    """
    Changelog shape that makes process_jira_event run a full Issue field sync.

    Uses the Sync In FPTR field id so the existing webhook code path applies.
    """
    field_id = JIRA_SYNC_IN_FPTR_FIELD.lower()
    if jira is not None:
        field_id = (
            jira.get_jira_issue_field_id(JIRA_SYNC_IN_FPTR_FIELD.lower()) or field_id
        )
    return {
        "items": [
            {
                "field": JIRA_SYNC_IN_FPTR_FIELD,
                "fieldId": field_id,
            }
        ]
    }


def _field_spec_to_changelog_item(field_spec, jira, require_value_strings=False):
    if not isinstance(field_spec, dict):
        raise JiraAutomationPayloadError("Each field entry must be an object.")

    field_name = _normalize_field_text(field_spec.get("field"))
    field_id = _normalize_field_text(field_spec.get("fieldId"))

    for value in (field_spec.get("field"), field_spec.get("fieldId")):
        if isinstance(value, str) and _looks_like_unexpanded_smart_value(value):
            raise JiraAutomationPayloadError(
                "field_change contains an unexpanded Jira smart value. "
                "Check the automation rule trigger (Field value changed) and "
                "Custom data. See docs/jira_automation.rst."
            )

    if require_value_strings:
        for key in ("fromString", "toString"):
            if key not in field_spec:
                raise JiraAutomationPayloadError(
                    f"field_change must include {key} "
                    f"(use {{{{fieldChange.{key}}}}})."
                )
            if isinstance(field_spec[key], str) and _looks_like_unexpanded_smart_value(
                field_spec[key]
            ):
                raise JiraAutomationPayloadError(
                    f"field_change.{key} is an unexpanded smart value."
                )

    if not field_name and not field_id:
        raise JiraAutomationPayloadError(
            "field_change needs fieldId (recommended, hard-code per rule) or field."
        )

    if not field_id and field_name and jira is not None:
        field_id = jira.get_jira_issue_field_id(field_name)

    if not field_name and field_id:
        field_name = field_id

    item = {
        "field": field_name,
        "fieldId": field_id or field_name,
    }
    for key in ("fromString", "toString", "from", "to"):
        if key in field_spec:
            item[key] = field_spec[key]
    return item


def _normalize_field_text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    text = value.strip()
    return text or None


def _looks_like_unexpanded_smart_value(value):
    return bool(re.match(_UNEXPANDED_SMART_VALUE_RE, value.strip()))
