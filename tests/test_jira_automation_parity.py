# Copyright 2026 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

"""
Jira Project Automation must behave like the site webhooks it replaces.

Each test sends a body shaped like a rule's *Custom data* through
:func:`~sg_jira.jira_automation_payload.normalize_automation_request` and the
Generic Syncer, and expects the outcome of the matching webhook test in
``test_entities_generic_handler``.
"""

import copy
import json
import unittest.mock as mock

import mock_jira
import mock_shotgun
import test_entities_generic_handler as handler_tests
import test_reply_sync as reply_tests
from test_sync_base import TestSyncBase

from sg_jira.constants import (
    JIRA_PROJECT_AUTOMATION_SOURCE,
    SHOTGUN_JIRA_ID_FIELD,
    SHOTGUN_JIRA_REPLY_IDS_FIELD,
)
from sg_jira.jira_automation_payload import (
    JiraAutomationPayloadError,
    normalize_automation_request,
)

BRIDGE_USER = mock_jira.JIRA_USER
HUMAN_USER = mock_jira.JIRA_USER_2


def automation_body(actor=HUMAN_USER, **fields):
    """A rule's Custom data, as the Jira smart values would expand."""
    return {
        "source": JIRA_PROJECT_AUTOMATION_SOURCE,
        "actor": {"accountId": actor["accountId"]},
        **fields,
    }


@mock.patch("shotgun_api3.Shotgun")
class TestAutomationParity(handler_tests.TestEntitiesGenericHandler):
    """Automation requests reach the same sync outcome as site webhooks."""

    def _sync(self, bridge, jira_issue, payload, name=None):
        event = normalize_automation_request(
            payload, "Issue", jira_issue.key, bridge.jira
        )
        return bridge.sync_in_shotgun(
            name or self.HANDLER_NAME, "Issue", jira_issue.key, event
        )

    def _issue_with_task(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        return bridge, jira_issue, mocked_sg_task

    # ------------------------------------------------------------------ Issue

    def test_partial_sync_updates_only_the_changed_field(self, mocked_sg):
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)

        payload = automation_body(
            field_change={
                "fieldId": "description",
                "fromString": "old",
                "toString": "new",
            }
        )
        self.assertTrue(self._sync(bridge, jira_issue, payload))

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            ["content", "sg_description"],
        )
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])
        self.assertNotEqual(jira_issue.fields.summary, sg_task["content"])

    def test_full_sync_updates_every_field_and_children(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        bridge.jira.add_comment(jira_issue, "jira comment body", author=HUMAN_USER)
        bridge.jira.add_worklog(
            jira_issue,
            timeSpentSeconds=0,
            comment="jira worklog body",
            author=HUMAN_USER,
        )
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertTrue(self._sync(bridge, jira_issue, automation_body()))

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            ["content", "sg_description"],
        )
        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])
        self.assertEqual(
            len(bridge.shotgun.find("Note", [["tasks", "is", mocked_sg_task]])), 1
        )
        self.assertEqual(
            len(bridge.shotgun.find("TimeLog", [["entity", "is", mocked_sg_task]])),
            1,
        )

    def test_full_sync_event_matches_the_webhook_a_user_would_send(self, mocked_sg):
        """The full sync marker is the same field the webhook test hard-codes."""
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)

        event = normalize_automation_request(
            automation_body(), "Issue", jira_issue.key, bridge.jira
        )

        webhook = self._mock_jira_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)
        self.assertEqual(event["webhookEvent"], webhook["webhookEvent"])
        self.assertEqual(event["issue"]["key"], jira_issue.key)
        self.assertEqual(event["changelog"]["items"][0]["fieldId"], "customfield_11504")

    def test_issue_changed_by_the_bridge_user_is_ignored(self, mocked_sg):
        """The actor drives the same loop protection as a webhook's ``user``."""
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)

        payload = automation_body(
            actor=BRIDGE_USER, field_change={"fieldId": "summary"}
        )
        self.assertFalse(self._sync(bridge, jira_issue, payload))

    def test_unsynced_issue_is_ignored(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(
            bridge, sg_entity=mock_shotgun.SG_TASK, sync_in_fptr="False"
        )
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertFalse(self._sync(bridge, jira_issue, automation_body()))

    # ---------------------------------------------------------------- Comment

    def test_comment_created_creates_a_note(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(
            jira_issue, body="comment body", author=HUMAN_USER
        )
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        payload = automation_body(
            event_type="comment_created", id=jira_comment.id, body="comment body"
        )
        self.assertTrue(self._sync(bridge, jira_issue, payload))

        sg_notes = bridge.shotgun.find(
            "Note", [["tasks", "is", mocked_sg_task]], [SHOTGUN_JIRA_ID_FIELD]
        )
        self.assertEqual(
            [n[SHOTGUN_JIRA_ID_FIELD] for n in sg_notes],
            ["%s/%s" % (jira_issue.key, jira_comment.id)],
        )

    def test_comment_authored_by_the_bridge_user_is_ignored(self, mocked_sg):
        """The author comes from Jira, so it can't be forged by the rule."""
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(
            jira_issue, body="comment body", author=BRIDGE_USER
        )
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        payload = automation_body(event_type="comment_created", id=jira_comment.id)
        self.assertFalse(self._sync(bridge, jira_issue, payload))
        self.assertEqual(
            bridge.shotgun.find("Note", [["tasks", "is", mocked_sg_task]]), []
        )

    def test_comment_body_is_loaded_for_reply_sync(self, mocked_sg):
        """Reply sync reads ``body`` from the event, a webhook always has it."""
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(
            jira_issue, body="a reply", author=HUMAN_USER
        )

        event = normalize_automation_request(
            automation_body(event_type="comment_created", id=jira_comment.id),
            "Issue",
            jira_issue.key,
            bridge.jira,
        )

        self.assertEqual(event["comment"]["body"], "a reply")

    def test_comment_entity_has_the_webhook_keys(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(
            jira_issue, body="a comment", author=HUMAN_USER
        )

        event = normalize_automation_request(
            automation_body(event_type="comment_created", id=jira_comment.id),
            "Issue",
            jira_issue.key,
            bridge.jira,
        )

        webhook = copy.deepcopy(mock_jira.COMMENT_PAYLOAD)
        self.assertTrue(set(webhook["comment"]) <= set(event["comment"]))
        self.assertTrue(set(webhook["issue"]) <= set(event["issue"]))
        self.assertEqual(
            event["comment"]["author"]["accountId"], HUMAN_USER["accountId"]
        )

    # ---------------------------------------------------------------- Worklog

    def test_worklog_created_creates_a_timelog(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(
            jira_issue, timeSpentSeconds=0, comment="fake comment", author=HUMAN_USER
        )
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        payload = automation_body(
            event_type="worklog_created",
            id=jira_worklog.id,
            comment="fake comment",
            timeSpentSeconds="0",
            timeSpent="0m",
        )
        self.assertTrue(self._sync(bridge, jira_issue, payload))

        sg_timelogs = bridge.shotgun.find(
            "TimeLog", [["entity", "is", mocked_sg_task]], [SHOTGUN_JIRA_ID_FIELD]
        )
        self.assertEqual(
            [t[SHOTGUN_JIRA_ID_FIELD] for t in sg_timelogs],
            ["%s/%s" % (jira_issue.key, jira_worklog.id)],
        )

    def test_worklog_deleted_deletes_the_timelog(self, mocked_sg):
        name = "entities_generic_both_way_deletion"
        syncer, bridge = self._get_syncer(mocked_sg, name=name)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(jira_issue, author=HUMAN_USER)
        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        jira_id = "%s/%s" % (jira_issue.key, jira_worklog.id)
        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["entity"] = [sg_mocked_task]
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = jira_id
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        # Once deleted, Jira can't be asked about the worklog any more.
        jira_worklog.delete()

        payload = automation_body(event_type="worklog_deleted", id=jira_worklog.id)
        self.assertTrue(self._sync(bridge, jira_issue, payload, name=name))

        self.assertEqual(
            bridge.shotgun.find("TimeLog", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_id]]),
            [],
        )

    def test_worklog_updated_updates_the_timelog(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(
            jira_issue, timeSpentSeconds=3600, comment="x", author=HUMAN_USER
        )
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        jira_id = "%s/%s" % (jira_issue.key, jira_worklog.id)
        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["entity"] = mocked_sg_task
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = jira_id
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)
        self.assertNotEqual(mocked_sg_timelog["duration"], 60)

        payload = automation_body(event_type="worklog_updated", id=jira_worklog.id)
        self.assertTrue(self._sync(bridge, jira_issue, payload))

        (sg_timelog,) = bridge.shotgun.find(
            "TimeLog", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_id]], ["duration"]
        )
        # FPTR durations are in minutes.
        self.assertEqual(sg_timelog["duration"], 60)

    def test_worklog_is_rejected_when_timelog_is_not_configured(self, mocked_sg):
        """The rejection reported for worklog rules on a bridge without TimeLog."""
        name = "entities_generic_no_timelog"
        syncer, bridge = self._get_syncer(mocked_sg, name=name)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(
            jira_issue, timeSpentSeconds=0, author=HUMAN_USER
        )
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        payload = automation_body(event_type="worklog_created", id=jira_worklog.id)
        with self.assertLogs(level="DEBUG") as logs:
            self.assertFalse(self._sync(bridge, jira_issue, payload, name=name))

        self.assertIn(
            "FPTR TimeLog is not configured for syncing", "\n".join(logs.output)
        )
        self.assertEqual(
            bridge.shotgun.find("TimeLog", [["entity", "is", mocked_sg_task]]), []
        )

    def test_worklog_authored_by_the_bridge_user_is_ignored(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(
            jira_issue, timeSpentSeconds=0, author=BRIDGE_USER
        )
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        payload = automation_body(event_type="worklog_created", id=jira_worklog.id)
        self.assertFalse(self._sync(bridge, jira_issue, payload))

    # ---------------------------------------------------- Comment update/delete

    def test_comment_updated_updates_the_note(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(
            jira_issue, body="body comment updated", author=HUMAN_USER
        )
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        jira_id = "%s/%s" % (jira_issue.key, jira_comment.id)
        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["tasks"] = [mocked_sg_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = jira_id
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)
        self.assertNotEqual(mocked_sg_note["content"], jira_comment.body)

        payload = automation_body(event_type="comment_updated", id=jira_comment.id)
        self.assertTrue(self._sync(bridge, jira_issue, payload))

        (sg_note,) = bridge.shotgun.find(
            "Note", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_id]], ["content"]
        )
        self.assertIn("body comment updated", sg_note["content"])

    def test_comment_deleted_deletes_the_note(self, mocked_sg):
        name = "entities_generic_both_way_deletion"
        syncer, bridge = self._get_syncer(mocked_sg, name=name)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(
            jira_issue, body="comment body", author=HUMAN_USER
        )
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        jira_id = "%s/%s" % (jira_issue.key, jira_comment.id)
        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["tasks"] = [mocked_sg_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = jira_id
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        # Once deleted, Jira can't be asked about the comment any more.
        jira_comment.delete()

        payload = automation_body(event_type="comment_deleted", id=jira_comment.id)
        self.assertTrue(self._sync(bridge, jira_issue, payload, name=name))

        self.assertEqual(
            bridge.shotgun.find("Note", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_id]]), []
        )

    def test_comment_deletion_is_ignored_when_deletion_sync_is_off(self, mocked_sg):
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)
        jira_comment = bridge.jira.add_comment(jira_issue, body="x", author=HUMAN_USER)
        jira_comment.delete()

        payload = automation_body(event_type="comment_deleted", id=jira_comment.id)
        self.assertFalse(self._sync(bridge, jira_issue, payload))

    # ------------------------------------------------------- Error handling

    def test_unknown_issue_is_a_payload_error(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        with self.assertRaisesRegex(JiraAutomationPayloadError, "NOPE-1"):
            normalize_automation_request(
                automation_body(), "Issue", "NOPE-1", bridge.jira
            )

    def test_unknown_comment_is_a_payload_error(self, mocked_sg):
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)

        payload = automation_body(event_type="comment_created", id="999")
        with self.assertRaisesRegex(JiraAutomationPayloadError, "was not found"):
            self._sync(bridge, jira_issue, payload)

    def test_unknown_worklog_is_a_payload_error(self, mocked_sg):
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)

        payload = automation_body(event_type="worklog_updated", id="999")
        with self.assertRaisesRegex(JiraAutomationPayloadError, "was not found"):
            self._sync(bridge, jira_issue, payload)

    def test_changed_field_the_bridge_does_not_map_is_not_synced(self, mocked_sg):
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)

        payload = automation_body(field_change={"fieldId": "customfield_unmapped"})
        self._sync(bridge, jira_issue, payload)

        sg_task = bridge.shotgun.find_one(
            "Task", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]], ["content"]
        )
        self.assertNotEqual(jira_issue.fields.summary, sg_task["content"])

    # ----------------------------------------------- Handler issue reference

    def test_issue_event_identified_by_key_only(self, mocked_sg):
        """The handler accepts an ``issue`` block without an id."""
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)
        event = self._mock_jira_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)
        event["issue"] = {"key": jira_issue.key}

        self.assertTrue(
            bridge.sync_in_shotgun(self.HANDLER_NAME, "Issue", jira_issue.key, event)
        )


@mock.patch("shotgun_api3.Shotgun")
class TestAutomationReplyParity(TestSyncBase):
    """Comment replies reach the same outcome as the webhook reply tests."""

    HANDLER_NAME = "entities_generic_with_reply"

    # Reuse the reply tests' fixtures without re-running their tests.
    _get_syncer = reply_tests.TestReplySync._get_syncer
    _mock_jira_data = reply_tests.TestReplySync._mock_jira_data
    _setup_common_sg_data = reply_tests.TestReplySync._setup_common_sg_data
    _setup_sg_task = reply_tests.TestReplySync._setup_sg_task
    _setup_sg_note = reply_tests.TestReplySync._setup_sg_note

    def _reply_scenario(self, bridge, body="new reply text"):
        self._setup_common_sg_data(bridge)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        created = bridge.jira.add_comment_reply(jira_issue.key, jira_comment.id, body)
        # The Jira mock keeps its own copy of the reply, the one to update.
        jira_reply = bridge.jira.comment(jira_issue.key, created.id)
        # Replies are made by people, not by the bridge.
        jira_reply.update(author={"accountId": HUMAN_USER["accountId"]})
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)
        return jira_issue, jira_reply, sg_note

    def _normalize(self, bridge, jira_issue, **fields):
        return normalize_automation_request(
            automation_body(**fields), "Issue", jira_issue.key, bridge.jira
        )

    def test_reply_created_creates_a_fptr_reply(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg)
        jira_issue, jira_reply, sg_note = self._reply_scenario(bridge)

        event = self._normalize(
            bridge, jira_issue, event_type="comment_created", id=jira_reply.id
        )
        self.assertTrue(
            bridge.sync_in_shotgun(self.HANDLER_NAME, "issue", jira_issue.key, event)
        )

        (reply,) = bridge.shotgun.find(
            "Reply",
            [["entity", "is", {"type": "Note", "id": sg_note["id"]}]],
            ["content"],
        )
        self.assertEqual(reply["content"], "new reply text")
        note = bridge.shotgun.find_one(
            "Note", [["id", "is", sg_note["id"]]], [SHOTGUN_JIRA_REPLY_IDS_FIELD]
        )
        self.assertIn(str(reply["id"]), json.loads(note[SHOTGUN_JIRA_REPLY_IDS_FIELD]))

    def test_reply_event_carries_parent_and_body_like_a_webhook(self, mocked_sg):
        syncer, bridge = self._get_syncer(mocked_sg)
        jira_issue, jira_reply, _ = self._reply_scenario(bridge)

        event = self._normalize(
            bridge, jira_issue, event_type="comment_created", id=jira_reply.id
        )

        self.assertEqual(event["comment"]["parentId"], jira_reply.parentId)
        self.assertEqual(event["comment"]["body"], "new reply text")

    def test_deleted_reply_cannot_be_told_from_a_deleted_comment(self, mocked_sg):
        """
        Known limitation: Jira can't be asked about a deleted comment, so the
        event has no ``parentId`` and is not routed to reply sync.
        """
        syncer, bridge = self._get_syncer(mocked_sg)
        jira_issue, jira_reply, _ = self._reply_scenario(bridge)
        jira_reply.delete()

        event = self._normalize(
            bridge, jira_issue, event_type="comment_deleted", id=jira_reply.id
        )

        self.assertNotIn("parentId", event["comment"])
