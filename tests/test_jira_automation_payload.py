# Copyright 2026 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
import copy
import os
import unittest.mock as mock

import mock_jira
from shotgun_api3.lib import mockgun
from test_sync_base import TestSyncBase

import sg_jira
from sg_jira.constants import (
    JIRA_EVENT_AUTOMATION_FULL_SYNC,
    SHOTGUN_JIRA_ID_FIELD,
    SHOTGUN_SYNC_IN_JIRA_FIELD,
)
from sg_jira.jira_automation_payload import (
    JiraAutomationPayloadError,
    normalize_automation_request,
)


@mock.patch("shotgun_api3.Shotgun")
class TestJiraAutomationPayload(TestSyncBase):
    """
    Test the normalization of Jira Project Automation "Send web request" bodies
    into the webhook-shaped events the handlers expect.
    """

    HANDLER_NAME = "entities_generic"

    # -- fixtures ----------------------------------------------------------

    def _get_bridge(self, mocked_sg):
        """
        Build a mocked Flow Production Tracking bridge, with the
        Asset entity granted the sync fields the generic handler needs.
        """
        sg = mockgun.Shotgun("https://mocked.my.com", "Ford Prefect", "xxxxxxxxxx")
        for sg_field in [SHOTGUN_SYNC_IN_JIRA_FIELD, SHOTGUN_JIRA_ID_FIELD]:
            new_field = copy.deepcopy(sg._schema["Task"][sg_field])
            new_field["entity_type"]["value"] = "Asset"
            sg._schema["Asset"][sg_field] = new_field
        mocked_sg.return_value = sg

        bridge = sg_jira.Bridge.get_bridge(
            os.path.join(self._fixtures_path, "settings.py")
        )

        bridge.get_syncer(self.HANDLER_NAME)
        return bridge

    def _bridge_with_issue(self, mocked_sg, issue_type_name="Task"):
        """Return a bridge with mocked Jira issue."""
        bridge = self._get_bridge(mocked_sg)
        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        issue = bridge.jira.create_issue(
            fields={"issuetype": bridge.jira.issue_type_by_name(issue_type_name)}
        )
        return bridge, issue

    def _payload(self, **extra):
        """
        A Jira Project Automation "Send web request" body: the ``source``
        sentinel plus the initiator's ``user`` block. ``extra`` overrides keys.
        """
        payload = {
            "source": "jira_project_automation",
            "user": {"accountId": "initiator-123"},
        }
        payload.update(extra)
        return payload

    # -- passthrough -------------------------------------------------------

    def test_non_automation_payloads_returned_unchanged(self, mocked_sg):
        """Anything without the automation ``source`` sentinel is untouched."""
        bridge = self._get_bridge(mocked_sg)
        payloads = [
            # a genuine Jira webhook
            {
                "webhookEvent": "jira:issue_updated",
                "issue": {"key": "DEV-1", "fields": {}},
            },
            # a PTR Event Daemon payload (carries `meta`, no `source`)
            {"meta": {"type": "attribute_change"}, "issue": {"fields": {}}},
            # anything else
            {"foo": "bar"},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertIs(
                    normalize_automation_request(bridge, "Issue", "DEV-1", payload),
                    payload,
                )

    def test_for_full_sync_without_flag_in_non_automation_body(self, mocked_sg):
        """

        A crafted webhook that lacks the ``source`` sentinel but sets the
        full-sync flag would otherwise pass through untouched and bypass the
        changelog requirement downstream. The flag must be stripped.

        """
        bridge = self._get_bridge(mocked_sg)
        payload = {
            "webhookEvent": "jira:issue_updated",
            "issue": {"key": "DEV-1", "fields": {}},
            JIRA_EVENT_AUTOMATION_FULL_SYNC: True,
        }

        result = normalize_automation_request(bridge, "Issue", "DEV-1", payload)

        self.assertNotIn(JIRA_EVENT_AUTOMATION_FULL_SYNC, result)

    def test_forged_full_sync_flag_overwritten_on_automation_request(self, mocked_sg):
        """
        A forged flag in a genuine automation body cannot pre-empt validation.

        Even a falsy forged value must be stripped and then set server-side, so
        acceptance never depends on the client-supplied flag.
        """
        bridge, issue = self._bridge_with_issue(mocked_sg)

        event = normalize_automation_request(
            bridge,
            "Issue",
            issue.key,
            self._payload(**{JIRA_EVENT_AUTOMATION_FULL_SYNC: False}),
        )

        self.assertTrue(event[JIRA_EVENT_AUTOMATION_FULL_SYNC])

    def test_non_dict_payload_returned_unchanged(self, mocked_sg):
        """A payload that is not a dictionary (malformed body) is untouched."""
        bridge = self._get_bridge(mocked_sg)
        for payload in ([], "string", 42, None):
            with self.subTest(payload=payload):
                self.assertIs(
                    normalize_automation_request(bridge, "Issue", "DEV-1", payload),
                    payload,
                )

    # -- happy path --------------------------------------------------------

    def test_minimal_payload_builds_full_sync_event(self, mocked_sg):
        """The minimal automation body yields a full-sync."""
        bridge, issue = self._bridge_with_issue(mocked_sg)

        event = normalize_automation_request(
            bridge, "Issue", issue.key, self._payload()
        )

        self.assertTrue(event[JIRA_EVENT_AUTOMATION_FULL_SYNC])
        # Without an explicit webhook_event, the event defaults to issue_updated.
        self.assertEqual(event["webhookEvent"], "jira:issue_updated")
        self.assertEqual(event["issue"]["id"], issue.raw["id"])
        self.assertEqual(event["issue"]["key"], issue.key)
        self.assertIsInstance(event["issue"]["fields"], dict)
        self.assertEqual(event["user"], {"accountId": "initiator-123"})

    def test_issue_created_webhook_event_honored(self, mocked_sg):
        """An explicit webhook_event of jira:issue_created is carried through."""
        bridge, issue = self._bridge_with_issue(mocked_sg)

        event = normalize_automation_request(
            bridge,
            "Issue",
            issue.key,
            self._payload(webhook_event="jira:issue_created"),
        )

        self.assertEqual(event["webhookEvent"], "jira:issue_created")
        self.assertTrue(event[JIRA_EVENT_AUTOMATION_FULL_SYNC])

    def test_non_dict_user_block_dropped(self, mocked_sg):
        """A ``user`` block that is not a dictionary is not forwarded."""
        bridge, issue = self._bridge_with_issue(mocked_sg)

        event = normalize_automation_request(
            bridge, "Issue", issue.key, self._payload(user="test_user")
        )
        self.assertNotIn("user", event)

    # -- rejections --------------------------------------------------------

    def test_malformed_requests_rejected(self, mocked_sg):
        """Malformed automation requests raise JiraAutomationPayloadError."""
        bridge, issue = self._bridge_with_issue(mocked_sg)

        cases = {
            "non-issue resource": ("Project", issue.key, self._payload()),
            "missing issue key": ("Issue", None, self._payload()),
            "invalid issue key format": ("Issue", "error in a key", self._payload()),
            "unknown issue": ("Issue", "DEV-404", self._payload()),
            "invalid webhook_event value": (
                "Issue",
                issue.key,
                self._payload(webhook_event="jira:issue_deleted"),
            ),
            "non-string webhook_event": (
                "Issue",
                issue.key,
                self._payload(webhook_event=123),
            ),
        }
        for name, (resource, key, payload) in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(JiraAutomationPayloadError):
                    normalize_automation_request(bridge, resource, key, payload)

    def test_malformed_jira_api_response_rejected(self, mocked_sg):
        """An issue whose raw Jira payload is malformed is rejected."""
        mutations = {
            "missing fields": lambda raw: raw.pop("fields"),
            "non-dict fields": lambda raw: raw.update(fields="not-an-object"),
            "missing id": lambda raw: raw.pop("id"),
            "invalid key": lambda raw: raw.update(key="nope"),
        }
        for name, mutate in mutations.items():
            with self.subTest(case=name):
                bridge, issue = self._bridge_with_issue(mocked_sg)
                issue_key = issue.key  # capture before mutating raw
                mutate(issue.raw)
                with self.assertRaises(JiraAutomationPayloadError):
                    normalize_automation_request(
                        bridge, "Issue", issue_key, self._payload()
                    )
