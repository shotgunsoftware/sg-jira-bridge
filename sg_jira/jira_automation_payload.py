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

    A request opts in by setting ``source`` to ``"jira_project_automation"``.
    For such requests the Jira issue is fetched and coerced into a webhook-shaped
    event; only ``Issue`` resources are supported. Any other payload is returned
    untouched so plain Jira webhooks keep working. In all cases the trusted
    full-sync flag is stripped from the inbound body so a client can never set
    it; it is only ever added server-side for genuine automation requests.

    :param bridge: The :class:`~sg_jira.Bridge` used to load the Jira issue.
    :param str resource_type: The Jira resource type from the URL path; must be
        ``Issue`` (case-insensitive) for automation requests.
    :param str resource_id: The Jira issue key from the URL path, e.g.
        ``PROJ-123``.
    :param payload: The parsed request body. Only a ``dict`` can be an
        automation request; any other type is returned unchanged.
    :returns: A webhook-shaped event ``dict`` for automation requests, otherwise
        the original ``payload`` unchanged.
    :raises JiraAutomationPayloadError: if the payload is a Jira Project
        Automation request but is malformed (unsupported resource type, missing
        or invalid issue key, unloadable issue, or bad ``webhook_event``). The
        caller should map it to HTTP 400.
    """

    if not isinstance(payload, dict):
        return payload

    # The full-sync flag is trusted downstream to bypass the changelog
    # requirement, so it must never be honored from an inbound body.
    payload.pop(JIRA_EVENT_AUTOMATION_FULL_SYNC, None)

    if payload.get("source") != "jira_project_automation":
        return payload

    if resource_type.lower() != "issue":
        raise JiraAutomationPayloadError(
            "Jira Project Automation sync only supports the Issue resource."
        )

    return _build_automation_event(bridge, resource_id, payload)


def _build_automation_event(bridge, issue_key, payload):
    """
    Build a webhook-shaped event from a validated Jira Project Automation body.

    The issue key comes from the URL path; the Jira issue is fetched from the
    bridge and coerced into the ``issue`` block the handlers expect. The event
    type is resolved from the optional ``webhook_event`` (defaulting to
    ``jira:issue_updated``) and the trusted full-sync flag is set server-side.

    :param bridge: The :class:`~sg_jira.Bridge` used to load the Jira issue.
    :param str issue_key: The Jira issue key, e.g. ``PROJ-123``.
    :param dict payload: The (source-validated) automation request body.
    :returns: A webhook-shaped event dictionary.
    :raises JiraAutomationPayloadError: if the issue key is missing or malformed,
        the Jira issue can't be loaded, or the Jira API response is unexpected.
    """

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
    """
    Resolve the webhook event type from an automation body.

    :param dict payload: The automation request body.
    :returns: The resolved webhook event type as a string.
    :raises JiraAutomationPayloadError: if ``webhook_event`` is not a string or
        is not an allowed value.
    """
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
    """
    Assemble the final webhook-shaped event.

    Sets the trusted full-sync flag server-side
    :param str webhook_event: The resolved webhook event type.
    :param dict issue_block: The coerced Jira ``issue`` block.
    :param dict payload: The automation request body.
    :returns: A webhook-shaped event dictionary.
    """
    event = {
        "webhookEvent": webhook_event,
        "issue": issue_block,
        JIRA_EVENT_AUTOMATION_FULL_SYNC: True,
    }
    user = payload.get("user")
    if isinstance(user, dict):
        event["user"] = user
    return event
