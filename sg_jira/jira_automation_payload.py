# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

"""
Normalize Jira Project Automation "Send web request" bodies into the
webhook-shaped events the existing handlers expect.

A request opts in by setting the ``source`` sentinel; any other payload is
returned unchanged so plain Jira webhooks keep working::

    {
        "source": "jira_project_automation",
        "user": {"accountId": "{{initiator.accountId}}"}
    }

The issue key comes from the URL path (``{{issue.key}}``); the bridge fetches
the issue from Jira and builds a webhook-shaped event. The optional ``user``
block is forwarded so loop-suppression can run, and an optional
``webhook_event`` (defaulting to ``jira:issue_updated``) selects the event type
for issue-created rules.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from jira import JIRAError

from .constants import (
    JIRA_EVENT_AUTOMATION_FULL_SYNC,
    JIRA_PROJECT_AUTOMATION_SOURCE,
)

logger = logging.getLogger(__name__)

# Project key + dash + number. Permissive on case/underscores to accommodate
# the variety of legal Jira project keys across Cloud and DC.
_ISSUE_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")

_ALLOWED_WEBHOOK_EVENTS = frozenset({"jira:issue_updated", "jira:issue_created"})
_DEFAULT_WEBHOOK_EVENT = "jira:issue_updated"

# Resource type expected in the URL path. Compared case-insensitively.
_SUPPORTED_RESOURCE_TYPE = "issue"


class JiraAutomationPayloadError(Exception):
    """Raised when a Jira Project Automation payload is malformed (HTTP 400)."""


def adapt_automation_request(
    bridge: Any,
    resource_type: str,
    resource_id: str | None,
    payload: Any,
) -> Any:
    """
    Return a webhook-shaped event if ``payload`` is a Jira Project Automation
    request; otherwise return ``payload`` unchanged.

    Only ``Issue`` resources are supported. A malformed automation payload
    raises :class:`JiraAutomationPayloadError`; the caller should map it to
    HTTP 400.
    """
    if not isinstance(payload, dict):
        return payload

    if payload.get("source") != JIRA_PROJECT_AUTOMATION_SOURCE:
        return payload

    if resource_type.lower() != _SUPPORTED_RESOURCE_TYPE:
        raise JiraAutomationPayloadError(
            "Jira Project Automation sync only supports the Issue resource."
        )

    url_issue_key = (resource_id or "").strip() or None
    return _normalize_automation(bridge, url_issue_key, payload)


def _normalize_automation(
    bridge: Any, url_issue_key: str | None, payload: dict[str, Any]
) -> dict[str, Any]:
    issue_key = _resolve_issue_key(payload.get("issue_key"), url_issue_key)
    webhook_event = _resolve_webhook_event(payload)

    try:
        jira_issue = bridge.jira.issue(issue_key)
    except JIRAError as e:
        raise JiraAutomationPayloadError(
            f"Unable to load Jira issue {issue_key}."
        ) from e

    raw = getattr(jira_issue, "raw", None)
    if not isinstance(raw, dict) or raw.get("fields") is None:
        raise JiraAutomationPayloadError(
            f"Unexpected Jira API response for {issue_key}."
        )

    issue_block = _build_issue_block(raw)
    logger.debug("Adapted automation request for %s", issue_key)
    return _build_event(webhook_event, issue_block, payload)


# --- Field-level resolvers -------------------------------------------------


def _resolve_issue_key(body_value: Any, url_issue_key: str | None) -> str:
    """Resolve and validate the issue key from the body or URL path."""
    if body_value is not None and not isinstance(body_value, str):
        raise JiraAutomationPayloadError("issue_key must be a string when provided.")
    candidate = (body_value or url_issue_key or "").strip()
    if not candidate:
        raise JiraAutomationPayloadError(
            "Missing issue key: set issue_key in the body or use it in the URL path."
        )
    if not _ISSUE_KEY_PATTERN.match(candidate):
        raise JiraAutomationPayloadError(
            "Invalid issue_key; expected a Jira key such as PROJ-123."
        )
    if url_issue_key and candidate != url_issue_key:
        raise JiraAutomationPayloadError(
            "issue key in the body must match the issue key in the URL path."
        )
    return candidate


def _resolve_webhook_event(payload: dict[str, Any]) -> str:
    webhook_event = payload.get("webhook_event", _DEFAULT_WEBHOOK_EVENT)
    if not isinstance(webhook_event, str):
        raise JiraAutomationPayloadError(
            "webhook_event must be a string when provided."
        )
    if webhook_event not in _ALLOWED_WEBHOOK_EVENTS:
        allowed = ", ".join(sorted(_ALLOWED_WEBHOOK_EVENTS))
        raise JiraAutomationPayloadError(f"webhook_event must be one of: {allowed}")
    return webhook_event


def _build_issue_block(issue_raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a Jira ``issue`` object into the webhook shape downstream needs."""
    fields = issue_raw.get("fields")
    if not isinstance(fields, dict):
        raise JiraAutomationPayloadError("issue.fields must be an object.")
    for required in ("id", "key"):
        if required not in issue_raw:
            raise JiraAutomationPayloadError(
                f"issue is missing required key {required}."
            )
    issue_key = issue_raw["key"]
    if not isinstance(issue_key, str) or not _ISSUE_KEY_PATTERN.match(issue_key):
        raise JiraAutomationPayloadError(
            "issue.key must be a Jira issue key (e.g. PROJ-123)."
        )
    return {
        "id": issue_raw["id"],
        "key": issue_key,
        "self": issue_raw.get("self"),
        "fields": fields,
    }


def _build_event(
    webhook_event: str, issue_block: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "webhookEvent": webhook_event,
        "issue": issue_block,
        JIRA_EVENT_AUTOMATION_FULL_SYNC: True,
    }
    user = payload.get("user")
    if isinstance(user, dict):
        event["user"] = user
    return event
