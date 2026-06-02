# Copyright 2024 Autodesk, Inc.  All rights reserved.
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
    JIRA_PROJECT_AUTOMATION_SOURCE,
    SHOTGUN_JIRA_ID_FIELD,
    SHOTGUN_SYNC_IN_JIRA_FIELD,
)
from sg_jira.jira_automation_payload import (
    JiraAutomationPayloadError,
    adapt_automation_request,
)


class TestJiraAutomationPayload(TestSyncBase):
    """
    Test the normalization of Jira Project Automation "Send web request" bodies
    into the webhook-shaped events the handlers expect.
    """

    HANDLER_NAME = "entities_generic"

    def _get_syncer(self, mocked_sg, name="task_issue"):
        """
        Helper to get a syncer and a bridge with a mocked Flow Production Tracking.
        We are overriding the method in this class to be able to patch the FPTR database and add more fields to the
        schema.

        :param mocked_sg: Mocked shotgun_api3.Shotgun.
        :parma str name: A syncer name.
        """

        sg = mockgun.Shotgun(
            "https://mocked.my.com",
            "Ford Prefect",
            "xxxxxxxxxx",
        )

        for sg_field in [SHOTGUN_SYNC_IN_JIRA_FIELD, SHOTGUN_JIRA_ID_FIELD]:
            new_field = copy.deepcopy(sg._schema["Task"][sg_field])
            new_field["entity_type"]["value"] = "Asset"
            sg._schema["Asset"][sg_field] = new_field

        mocked_sg.return_value = sg
        bridge = sg_jira.Bridge.get_bridge(
            os.path.join(self._fixtures_path, "settings.py")
        )
        syncer = bridge.get_syncer(name)
        return syncer, bridge

    def _mock_jira_data(self, bridge, issue_type_name="Task"):
        """
        Helper method to mock Jira data.
        We can't call it in the `setUp` method as we need the bridge instance...
        """
        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        return bridge.jira.create_issue(
            fields={"issuetype": bridge.jira.issue_type_by_name(issue_type_name)}
        )

    def _automation_payload(self, account_id="initiator-123", **extra):
        """
        Helper method to mock a Jira Project Automation "Send web request" body.

        Mirrors what the automation rule actually posts: the ``source`` sentinel
        and the initiator's ``user`` block. The issue key is taken from the URL
        path (``{{issue.key}}``), not the body. Extra keys (e.g. ``issue_key``
        or ``webhook_event``) can be supplied to exercise the optional overrides.
        """
        payload = {
            "source": JIRA_PROJECT_AUTOMATION_SOURCE,
            "user": {"accountId": account_id},
        }
        payload.update(extra)
        return payload


# Mock Flow Production Tracking with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
class TestJiraAutomationPayloadPassthrough(TestJiraAutomationPayload):
    """Payloads that are not opt-in automation shapes are returned unchanged."""

    def test_non_dict_payload_returned_unchanged(self, mocked_sg):
        """A payload that is not a dictionary is returned untouched."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        for payload in ([], "string", 42, None):
            self.assertIs(
                adapt_automation_request(bridge, "Issue", "DEV-1", payload), payload
            )

    def test_real_webhook_payload_left_alone(self, mocked_sg):
        """A genuine webhook already has webhookEvent and must not be reshaped."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        payload = {
            "webhookEvent": "jira:issue_updated",
            "issue": {"key": "DEV-1", "fields": {}},
        }
        self.assertIs(
            adapt_automation_request(bridge, "Issue", "DEV-1", payload), payload
        )

    def test_event_daemon_payload_with_meta_left_alone(self, mocked_sg):
        """
        PTR Event Daemon payloads carry `meta` and no `source` sentinel, so they
        must be returned untouched.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        payload = {"meta": {"type": "attribute_change"}, "issue": {"fields": {}}}
        self.assertIs(
            adapt_automation_request(bridge, "Issue", "DEV-1", payload), payload
        )

    def test_unrelated_payload_left_alone(self, mocked_sg):
        """A payload that matches no opt-in shape is returned untouched."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        payload = {"foo": "bar"}
        self.assertIs(
            adapt_automation_request(bridge, "Issue", "DEV-1", payload), payload
        )


@mock.patch("shotgun_api3.Shotgun")
class TestJiraAutomationPayloadMinimalBody(TestJiraAutomationPayload):
    """The ``source == jira_project_automation`` minimal-body path."""

    def test_minimal_automation_payload_with_url_key(self, mocked_sg):
        """
        The real automation payload only carries ``source`` and the initiator's
        ``user`` block; the issue key comes from the URL path ({{issue.key}}).
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge)

        payload = self._automation_payload(account_id="initiator-123")
        event = adapt_automation_request(bridge, "Issue", jira_issue.key, payload)

        self.assertEqual(event["webhookEvent"], "jira:issue_updated")
        self.assertTrue(event[JIRA_EVENT_AUTOMATION_FULL_SYNC])
        self.assertEqual(event["issue"]["key"], jira_issue.key)
        self.assertEqual(event["issue"]["id"], jira_issue.raw["id"])
        self.assertIsInstance(event["issue"]["fields"], dict)
        # The initiator's user block is forwarded so loop-suppression can run.
        self.assertEqual(event["user"], {"accountId": "initiator-123"})

    def test_issue_key_from_body(self, mocked_sg):
        """The issue key may optionally be provided in the request body."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge)

        payload = self._automation_payload(issue_key=jira_issue.key)
        event = adapt_automation_request(bridge, "Issue", None, payload)

        self.assertEqual(event["issue"]["key"], jira_issue.key)
        self.assertEqual(event["user"], {"accountId": "initiator-123"})

    def test_webhook_event_created_honored(self, mocked_sg):
        """The webhook_event can be overridden to jira:issue_created."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge)

        payload = self._automation_payload(webhook_event="jira:issue_created")
        event = adapt_automation_request(bridge, "Issue", jira_issue.key, payload)
        self.assertEqual(event["webhookEvent"], "jira:issue_created")

    def test_user_block_passed_through(self, mocked_sg):
        """The initiator's user block is forwarded to the normalized event."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge)

        payload = self._automation_payload(account_id="abc")
        event = adapt_automation_request(bridge, "Issue", jira_issue.key, payload)
        self.assertEqual(event["user"], {"accountId": "abc"})

    def test_non_dict_user_block_dropped(self, mocked_sg):
        """A user block that is not a dictionary is dropped from the event."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge)

        payload = self._automation_payload()
        payload["user"] = "not-a-dict"
        event = adapt_automation_request(bridge, "Issue", jira_issue.key, payload)
        self.assertNotIn("user", event)

    def test_invalid_webhook_event_rejected(self, mocked_sg):
        """An unsupported webhook_event value is rejected."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        payload = self._automation_payload(webhook_event="jira:issue_deleted")
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Issue", "DEV-25", payload)

    def test_non_string_webhook_event_rejected(self, mocked_sg):
        """A non-string webhook_event value is rejected."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        payload = self._automation_payload(webhook_event=123)
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Issue", "DEV-25", payload)

    def test_missing_issue_key_rejected(self, mocked_sg):
        """An automation payload without an issue key (body or URL) is rejected."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        payload = self._automation_payload()
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Issue", None, payload)

    def test_non_string_issue_key_rejected(self, mocked_sg):
        """A non-string issue_key value in the body is rejected."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        payload = self._automation_payload(issue_key=25)
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Issue", None, payload)

    def test_invalid_issue_key_format_rejected(self, mocked_sg):
        """An issue key (from the URL path) that isn't a Jira key is rejected."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        payload = self._automation_payload()
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Issue", "not a key", payload)

    def test_body_url_key_mismatch_rejected(self, mocked_sg):
        """An issue key in the body that differs from the URL path is rejected."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        payload = self._automation_payload(issue_key="DEV-25")
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Issue", "DEV-99", payload)

    def test_jira_lookup_error_wrapped(self, mocked_sg):
        """A Jira lookup failure is wrapped in a JiraAutomationPayloadError."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])

        # DEV-404 is a valid key shape but was never created in the mocked Jira.
        payload = self._automation_payload()
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Issue", "DEV-404", payload)

    def test_unexpected_api_response_rejected(self, mocked_sg):
        """A Jira response without a `fields` block is rejected."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge)
        del jira_issue.raw["fields"]

        payload = self._automation_payload()
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Issue", jira_issue.key, payload)

    def test_api_response_with_non_dict_fields_rejected(self, mocked_sg):
        """A Jira response whose `fields` is not an object is rejected."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge)
        jira_issue.raw["fields"] = "not-an-object"

        payload = self._automation_payload()
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Issue", jira_issue.key, payload)

    def test_api_response_missing_id_rejected(self, mocked_sg):
        """A Jira response missing the issue id is rejected."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge)
        del jira_issue.raw["id"]

        payload = self._automation_payload()
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Issue", jira_issue.key, payload)

    def test_api_response_with_invalid_key_rejected(self, mocked_sg):
        """A Jira response whose key is not a Jira issue key is rejected."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge)
        issue_key = jira_issue.key
        jira_issue.raw["key"] = "nope"

        payload = self._automation_payload()
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Issue", issue_key, payload)

    def test_non_issue_resource_rejected(self, mocked_sg):
        """Only the Issue resource type is supported."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        payload = self._automation_payload()
        with self.assertRaises(JiraAutomationPayloadError):
            adapt_automation_request(bridge, "Project", "DEV", payload)
