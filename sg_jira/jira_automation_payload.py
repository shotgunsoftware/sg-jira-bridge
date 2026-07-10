# Copyright 2026 Autodesk, Inc.  All rights reserved.
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

import logging
import re

from jira import JIRAError

from .constants import (
    JIRA_EVENT_AUTOMATION_FULL_SYNC,
)

logger = logging.getLogger(__name__)

# Project key + dash + number. Permissive on case/underscores to accommodate
# the variety of legal Jira project keys across Cloud and DC.
_ISSUE_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")

_ALLOWED_WEBHOOK_EVENTS = frozenset({"jira:issue_updated", "jira:issue_created"})


class JiraAutomationPayloadError(Exception):
    """Raised when a Jira Project Automation payload is malformed (HTTP 400)."""


def normalize_automation_request(bridge, resource_type, resource_id, payload):
    """
    Return a webhook-shaped event if ``payload`` is a Jira Project Automation
    request; otherwise return ``payload`` unchanged.

    Only ``Issue`` resources are supported. A malformed automation payload
    raises :class:`JiraAutomationPayloadError`; the caller should map it to
    HTTP 400.
    """

    if payload.get("source") != "jira_project_automation":
        return payload

    if resource_type.lower() != "issue":
        raise JiraAutomationPayloadError(
            "Jira Project Automation sync only supports the Issue resource."
        )

    return _build_automation_event(bridge, resource_id, payload)


def _build_automation_event(bridge, issue_key, payload):

    if not issue_key:
        raise JiraAutomationPayloadError(
            "Missing issue key: set issue_key in the URL path."
        )

    if not _ISSUE_KEY_PATTERN.match(issue_key):
        raise JiraAutomationPayloadError(
            "Invalid issue_key; expected a Jira key such as PROJ-123."
        )

    webhook_event = _resolve_webhook_event(payload)

    try:
        jira_issue = bridge.jira.issue(issue_key)
    except JIRAError as e:
        raise JiraAutomationPayloadError(
            f"Unable to load Jira issue {issue_key}."
        ) from e

    raw = getattr(jira_issue, "raw", None)
    if not isinstance(raw, dict):
        raise JiraAutomationPayloadError(
            f"Unexpected Jira API response for {issue_key}."
        )

    issue_block = _build_issue_block(raw)
    logger.debug("Normalized automation request for %s", issue_key)
    return _build_event(webhook_event, issue_block, payload)


# --- Field-level resolvers -------------------------------------------------


def _resolve_webhook_event(payload):
    webhook_event = payload.get("webhook_event", "jira:issue_updated")
    if not isinstance(webhook_event, str):
        raise JiraAutomationPayloadError(
            "webhook_event must be a string when provided."
        )
    if webhook_event not in _ALLOWED_WEBHOOK_EVENTS:
        allowed = ", ".join(sorted(_ALLOWED_WEBHOOK_EVENTS))
        raise JiraAutomationPayloadError(f"webhook_event must be one of: {allowed}")
    return webhook_event


def _build_issue_block(issue_raw):
    """Coerce a Jira ``issue`` object into the webhook shape downstream needs."""
    fields = issue_raw.get("fields")
    if not isinstance(fields, dict):
        raise JiraAutomationPayloadError("issue.fields must be an object.")

    missing = {"id", "key"} - issue_raw.keys()
    if missing:
        raise JiraAutomationPayloadError(
            f"issue is missing required key(s): {', '.join(sorted(missing))}."
        )

    issue_key = issue_raw["key"]
    if not _ISSUE_KEY_PATTERN.match(issue_key):
        raise JiraAutomationPayloadError(
            "issue.key must be a Jira issue key (e.g. PROJ-123)."
        )
    return {
        "id": issue_raw["id"],
        "key": issue_key,
        "self": issue_raw.get("self"),
        "fields": fields,
    }


def _build_event(webhook_event, issue_block, payload):
    event = {
        "webhookEvent": webhook_event,
        "issue": issue_block,
        JIRA_EVENT_AUTOMATION_FULL_SYNC: True,
    }
    user = payload.get("user")
    if isinstance(user, dict):
        event["user"] = user
    return event
