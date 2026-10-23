# Copyright 2026 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

"""
Normalize Jira Project Automation web-request bodies into webhook-shaped events.

Site webhooks carry a native ``changelog`` and fully populated ``comment`` /
``worklog`` blocks; Project Automation sends only what the rule's *Custom data*
contains. This module converts that small body into the event a site webhook
would have produced, so the Generic Syncer handles both identically.

Three body shapes are supported (see :doc:`jira_automation`):

* Issue full sync: ``source`` + ``actor``.
* Issue partial sync: the above + ``field_change``.
* Comment / worklog: ``source`` + ``actor`` + ``event_type`` (``{{eventType}}``) + ``id``,
  with optional ``body`` (comment) or ``comment`` / ``timeSpentSeconds`` /
  ``timeSpent`` (worklog).

Anything else is rejected, so rule typos surface in the Jira audit log instead
of silently syncing the wrong thing.
"""

import logging

from jira import JIRAError

from sg_jira.constants import (
    JIRA_PROJECT_AUTOMATION_SOURCE,
    JIRA_SYNC_IN_FPTR_FIELD,
)

logger = logging.getLogger(__name__)

# ``{{eventType}}`` value -> (entity kind, action), named like site webhooks.
_ENTITY_EVENTS = {
    "comment_created": ("comment", "created"),
    "comment_updated": ("comment", "updated"),
    "comment_deleted": ("comment", "deleted"),
    "worklog_created": ("worklog", "created"),
    "worklog_updated": ("worklog", "updated"),
    "worklog_deleted": ("worklog", "deleted"),
}

# Issue created and updated events are handled identically by the syncer, so
# automation always emits the update event.
_ISSUE_WEBHOOK_EVENT = "jira:issue_updated"

_COMMON_KEYS = frozenset({"source", "actor"})
_ISSUE_KEYS = _COMMON_KEYS | {"field_change"}
_ENTITY_KEYS = _COMMON_KEYS | {"event_type", "id"}
_ENTITY_OPTIONAL_KEYS = {
    "comment": frozenset({"body"}),
    "worklog": frozenset({"comment", "timeSpentSeconds", "timeSpent"}),
}
_FIELD_CHANGE_KEYS = frozenset({"fieldId", "field", "fromString", "toString"})


class JiraAutomationPayloadError(ValueError):
    """Raised when a Jira Project Automation request body is invalid."""


def is_automation_request(payload):
    """
    Return whether the given request body was sent by a Project Automation rule.

    :param payload: Parsed JSON request body.
    :rtype: bool
    """
    return (
        isinstance(payload, dict)
        and payload.get("source") == JIRA_PROJECT_AUTOMATION_SOURCE
    )


def normalize_automation_request(payload, resource_type, resource_id, jira):
    """
    Convert a Project Automation POST body into an event the Generic Syncer accepts.

    :param dict payload: Parsed JSON request body, see :func:`is_automation_request`.
    :param str resource_type: Jira resource type from the URL path (``issue``).
    :param str resource_id: Jira Issue key from the URL path.
    :param jira: A connected :class:`~sg_jira.jira_session.JiraSession`.
    :returns: Event dictionary in Jira webhook shape.
    :raises JiraAutomationPayloadError: If the request is invalid.
    """
    if not is_automation_request(payload):
        raise JiraAutomationPayloadError(
            f'Request body must be a JSON object with "source": '
            f'"{JIRA_PROJECT_AUTOMATION_SOURCE}".'
        )
    if not isinstance(resource_type, str) or resource_type.lower() != "issue":
        raise JiraAutomationPayloadError(
            "Jira Project Automation only supports Issue resources in the URL path."
        )
    if not resource_id or not isinstance(resource_id, str):
        raise JiraAutomationPayloadError(
            "The request path must include a Jira Issue key."
        )

    actor = _parse_actor(payload)
    event_type = _parse_event_type(payload)

    issue_ref = _issue_reference(jira, resource_id)
    if event_type is None:
        event = _issue_event(payload, issue_ref, jira)
    else:
        event = _entity_event(payload, event_type, issue_ref, jira)
    # Site webhooks carry the initiator as ``user``; the syncer relies on it to
    # ignore changes made by the bridge itself.
    event["user"] = actor

    logger.debug("Normalized Jira automation request for %s: %s", resource_id, event)
    return event


def _parse_actor(payload):
    """
    Return the initiator of the rule as the ``user`` of a webhook event.

    The syncer uses it to ignore the changes made by the bridge itself, so it is
    required.

    :param dict payload: The request body.
    :returns: A dictionary with the ``accountId`` of the initiator.
    :raises JiraAutomationPayloadError: If the actor is missing or has no account
        id, for instance when Jira had no user to render ``{{initiator.accountId}}``.
    """
    actor = payload.get("actor")
    if not isinstance(actor, dict):
        raise JiraAutomationPayloadError(
            'actor is required, e.g. "actor": {"accountId": "{{initiator.accountId}}"}.'
        )
    account_id = actor.get("accountId")
    if not account_id:
        raise JiraAutomationPayloadError(
            "actor.accountId is empty. The rule must be triggered by a user, "
            "otherwise the bridge cannot ignore its own changes."
        )
    _require_string("actor.accountId", account_id)
    return {"accountId": account_id}


def _parse_event_type(payload):
    """
    Return the ``event_type`` of a comment or worklog rule.

    :param dict payload: The request body.
    :returns: The lower case event name, such as ``comment_created``, or None if
        the body has no ``event_type``, which is the case of Issue rules.
    :raises JiraAutomationPayloadError: If the event type is not one of
        comment/worklog ones.
    """
    event_type = payload.get("event_type")
    if not event_type:
        return None
    _require_string("event_type", event_type)
    key = event_type.lower()
    if key not in _ENTITY_EVENTS:
        raise JiraAutomationPayloadError(
            f"Unsupported event_type {event_type!r}. event_type is only used by "
            f"comment/worklog rules ({', '.join(sorted(_ENTITY_EVENTS))}); "
            f"omit it for Issue rules."
        )
    return key


def _issue_reference(jira, issue_key):
    """
    Return the ``issue`` block of a webhook, which has the key and the id of the Issue.

    :param jira: A :class:`~sg_jira.jira_session.JiraSession`.
    :param str issue_key: The key of the Issue, from the request path.
    :returns: A dictionary with the ``key`` and the ``id`` of the Issue.
    :raises JiraAutomationPayloadError: If Jira has no such Issue.
    :raises jira.JIRAError: For any other Jira failure, which is not the fault of
        the request.
    """
    try:
        issue = jira.issue(issue_key, fields="id")
    except JIRAError as e:
        if e.status_code == 404:
            raise JiraAutomationPayloadError(
                f"Jira Issue {issue_key!r} was not found."
            ) from e
        # Auth, rate limit or outage: not the caller's fault, let it surface.
        raise
    # The path may hold the key in another case, or the id: Jira knows the key.
    return {"key": getattr(issue, "key", None) or issue_key, "id": str(issue.id)}


def _issue_event(payload, issue_ref, jira):
    """
    Build the event of an Issue rule.

    A ``field_change`` makes it a partial sync of that field, otherwise it is a
    full sync of the Issue.

    :param dict payload: The request body.
    :param dict issue_ref: The ``issue`` block of the event.
    :param jira: A :class:`~sg_jira.jira_session.JiraSession`.
    :returns: An Issue update event, in the shape of a webhook payload.
    :raises JiraAutomationPayloadError: If the body has keys Issue rules do not take,
        or an invalid ``field_change``.
    """
    _check_keys(payload, _ISSUE_KEYS)

    if "field_change" in payload:
        items = [_field_change_item(payload["field_change"])]
    else:
        items = [_full_sync_item(jira)]
    return {
        "webhookEvent": _ISSUE_WEBHOOK_EVENT,
        "issue": issue_ref,
        "changelog": {"items": items},
    }


def _full_sync_item(jira):
    """
    Changelog item which makes the handler run a full Issue field sync.

    The handler treats a change to the *Sync In FPTR* field as "sync everything".
    """
    field_id = jira.get_jira_issue_field_id(JIRA_SYNC_IN_FPTR_FIELD.lower())
    if not field_id:
        raise RuntimeError(
            f"Jira field {JIRA_SYNC_IN_FPTR_FIELD!r} was not found. "
            f"Is it set up in Jira?"
        )
    return {"field": JIRA_SYNC_IN_FPTR_FIELD, "fieldId": field_id}


def _field_change_item(field_change):
    """
    Build a webhook changelog item from the ``field_change`` of a rule.

    Only the field matters to the syncer, which reads its new value from Jira.
    ``fromString`` and ``toString`` are kept for tracing.

    :param field_change: The ``field_change`` value of the request body.
    :returns: A dictionary with the ``field`` and ``fieldId`` of the changed field.
    :raises JiraAutomationPayloadError: If it is not an object, has unknown keys, or
        has no ``fieldId``.
    """
    if not isinstance(field_change, dict):
        raise JiraAutomationPayloadError("field_change must be an object.")
    _check_keys(field_change, _FIELD_CHANGE_KEYS, "field_change")

    field_id = field_change.get("fieldId")
    if not field_id:
        raise JiraAutomationPayloadError(
            'field_change.fieldId is required, e.g. "{{fieldChange.fieldId}}", '
            "or hard-code the field id in the rule."
        )
    _require_string("field_change.fieldId", field_id)
    name = field_change.get("field")
    if name:
        _require_string("field_change.field", name)

    item = {"field": name or field_id, "fieldId": field_id}
    # The syncer only needs the field; these mirror a webhook for traceability.
    for key in ("fromString", "toString"):
        if key in field_change:
            item[key] = field_change[key]
    return item


def _entity_event(payload, event_type, issue_ref, jira):
    """
    Build the event of a comment or worklog rule.

    The comment or worklog is read back from Jira, which is the source of truth, so
    what the rule sent only completes what Jira does not provide. A deleted one
    cannot be read, so the event has only what the rule sent, like a webhook has.

    :param dict payload: The request body.
    :param str event_type: A key of ``_ENTITY_EVENTS``.
    :param dict issue_ref: The ``issue`` block of the event.
    :param jira: A :class:`~sg_jira.jira_session.JiraSession`.
    :returns: A ``comment_*`` or ``worklog_*`` event, in the shape of a webhook payload.
    :raises JiraAutomationPayloadError: If the body has keys these rules do not take,
        has no ``id``, or refers to a comment or worklog Jira does not have.
    """
    kind, action = _ENTITY_EVENTS[event_type]
    optional_keys = _ENTITY_OPTIONAL_KEYS[kind]
    _check_keys(payload, _ENTITY_KEYS | optional_keys)

    entity_id = payload.get("id")
    if not entity_id:
        raise JiraAutomationPayloadError(
            f'{event_type} requires "id": "{{{{{kind}.id}}}}".'
        )
    # Jira sends ids as strings, a rule may send a number.
    if isinstance(entity_id, bool) or not isinstance(entity_id, (str, int)):
        raise JiraAutomationPayloadError(
            f"id must be a string or an integer, got {entity_id!r}."
        )
    # What the rule sent is only a fallback: Jira is the source of truth.
    entity = {key: payload[key] for key in optional_keys if key in payload}
    entity["id"] = entity_id

    # A deleted comment or worklog cannot be read: a webhook only carries its id.
    if action != "deleted":
        entity.update(_load_entity(jira, kind, issue_ref["key"], entity_id))
    if kind == "worklog":
        # Always the numeric id of the Issue, whatever the action, like a webhook.
        entity["issueId"] = issue_ref["id"]

    return {"webhookEvent": event_type, "issue": issue_ref, kind: entity}


def _load_entity(jira, kind, issue_key, entity_id):
    """
    Read a comment or worklog from Jira, shaped like the one of a webhook.

    :param jira: A :class:`~sg_jira.jira_session.JiraSession`.
    :param str kind: ``comment`` or ``worklog``.
    :param str issue_key: The key of the Issue it belongs to.
    :param entity_id: The id of the comment or worklog.
    :returns: The ``comment`` or ``worklog`` block of the event.
    :raises JiraAutomationPayloadError: If Jira has no such comment or worklog.
    """
    loader = getattr(jira, f"{kind}_as_webhook_entity")
    try:
        return loader(issue_key, entity_id)
    except ValueError as e:
        raise JiraAutomationPayloadError(str(e)) from e


def _require_string(name, value):
    """
    Check that a value of the request body is a string.

    :param str name: The key of the value, for the error message.
    :param value: The value to check.
    :raises JiraAutomationPayloadError: If it is not a string.
    """
    if not isinstance(value, str):
        raise JiraAutomationPayloadError(f"{name} must be a string, got {value!r}.")


def _check_keys(data, allowed, name="Automation body"):
    """
    Reject keys which are not allowed, so that a typo in a rule is reported.

    :param dict data: The dictionary to check.
    :param allowed: The keys it may have.
    :param str name: What the dictionary is, for the error message.
    :raises JiraAutomationPayloadError: If there are other keys.
    """
    unexpected = set(data) - allowed
    if unexpected:
        raise JiraAutomationPayloadError(
            f"{name} has unexpected keys: {', '.join(sorted(unexpected))}. "
            f"Allowed: {', '.join(sorted(allowed))}."
        )
