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
``test_entities_generic_handler`` or ``test_reply_sync``. The normalizer alone is
covered by ``test_jira_automation_payload``.
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

# The Jira user the bridge runs as: what it does itself must never come back.
BRIDGE_USER = mock_jira.JIRA_USER
# A person working in Jira.
HUMAN_USER = mock_jira.JIRA_USER_2


def automation_body(actor=HUMAN_USER, **fields):
    """
    Return the *Custom data* of a rule, as Jira would send it once expanded.

    :param dict actor: The Jira user who made the change.
    :param fields: The other keys of the body, for instance ``field_change``.
    """
    return {
        "source": JIRA_PROJECT_AUTOMATION_SOURCE,
        "actor": {"accountId": actor["accountId"]},
        **fields,
    }


@mock.patch("shotgun_api3.Shotgun")
class TestAutomationParity(handler_tests.TestEntitiesGenericHandler):
    """Automation requests reach the same sync outcome as site webhooks."""

    def _sync(self, bridge, jira_issue, payload, name=None):
        """
        Normalize ``payload`` and sync the resulting event in Flow Production Tracking.

        :returns: True if the event was synced, False if it was rejected.
        :raises JiraAutomationPayloadError: If the body is invalid.
        """
        event = normalize_automation_request(
            payload, "Issue", jira_issue.key, bridge.jira
        )
        return bridge.sync_in_shotgun(
            name or self.HANDLER_NAME, "Issue", jira_issue.key, event
        )

    def _issue_with_task(self, mocked_sg):
        """Return a bridge, a synced Jira Issue and its FPTR Task."""
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        return bridge, jira_issue, mocked_sg_task

    # -------------------------------------------------------------------------------
    # Issue - partial sync
    # -------------------------------------------------------------------------------

    def test_automation_issue_partial_sync_one_field_only(self, mocked_sg):
        """
        Check that only the field which changed in Jira is updated in FPTR.

        Test environment:
        - the Issue is flagged as ready to sync and already exists in FPTR
        - the rule sends a ``field_change`` for the description
        Expected result:
        - the description is updated in FPTR
        - the summary, which did not change, is not
        """
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

    def test_automation_issue_partial_sync_unmapped_field_ignored(self, mocked_sg):
        """
        Check that a change to a field which is not mapped syncs nothing.

        Expected result:
        - the FPTR Task is left as it was
        """
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)

        payload = automation_body(field_change={"fieldId": "customfield_unmapped"})
        self._sync(bridge, jira_issue, payload)

        sg_task = bridge.shotgun.find_one(
            "Task", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]], ["content"]
        )
        self.assertNotEqual(jira_issue.fields.summary, sg_task["content"])

    # -------------------------------------------------------------------------------
    # Issue - full sync
    # -------------------------------------------------------------------------------

    def test_automation_issue_full_sync_all_fields_and_children(self, mocked_sg):
        """
        Check that a full sync updates every field, and the comments and worklogs.

        Test environment:
        - the Issue is flagged as ready to sync and already exists in FPTR
        - it has a comment and a worklog made by a person
        Expected result:
        - all the mapped fields are updated
        - one FPTR Note and one TimeLog are created
        """
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

    def test_automation_issue_full_sync_event_matches_webhook(self, mocked_sg):
        """
        Check that a full sync event is the one a webhook of the same change gives.

        Expected result:
        - same event name, same Issue
        - the changelog is a change of the Sync In FPTR field, whose id is the one
          the webhook tests hard code
        """
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)

        event = normalize_automation_request(
            automation_body(), "Issue", jira_issue.key, bridge.jira
        )

        webhook = self._mock_jira_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)
        self.assertEqual(event["webhookEvent"], webhook["webhookEvent"])
        self.assertEqual(event["issue"]["key"], jira_issue.key)
        self.assertEqual(event["changelog"]["items"][0]["fieldId"], "customfield_11504")

    def test_automation_issue_not_flagged_as_synced_rejected(self, mocked_sg):
        """
        Check that an Issue which is not flagged as synced is ignored.

        Expected result:
        - the event is rejected
        """
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(
            bridge, sg_entity=mock_shotgun.SG_TASK, sync_in_fptr="False"
        )
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertFalse(self._sync(bridge, jira_issue, automation_body()))

    def test_automation_issue_changed_by_jira_bridge_user_rejected(self, mocked_sg):
        """
        Check that the changes made by the bridge itself are not synced back.

        Test environment:
        - the actor of the rule is the Jira user the bridge runs as
        Expected result:
        - the event is rejected, to avoid an infinite loop
        """
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)

        payload = automation_body(
            actor=BRIDGE_USER, field_change={"fieldId": "summary"}
        )

        self.assertFalse(self._sync(bridge, jira_issue, payload))

    def test_automation_issue_event_identified_by_key_only(self, mocked_sg):
        """
        Check that the handler accepts an ``issue`` block which has no id.

        Expected result:
        - the Issue is found with its key and synced
        """
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)
        event = self._mock_jira_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)
        event["issue"] = {"key": jira_issue.key}

        self.assertTrue(
            bridge.sync_in_shotgun(self.HANDLER_NAME, "Issue", jira_issue.key, event)
        )

    # -------------------------------------------------------------------------------
    # Comment
    # -------------------------------------------------------------------------------

    def test_automation_comment_created_creates_note(self, mocked_sg):
        """
        Check that the FPTR Note associated to the Jira comment is created.

        Test environment:
        - the Issue is flagged as ready to sync
        - the comment was made by a person
        Expected result:
        - one Note is created, linked to the comment
        """
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

    def test_automation_comment_updated_updates_note(self, mocked_sg):
        """
        Check that the FPTR Note associated to the Jira comment is updated.

        Expected result:
        - the content of the Note is the new text of the comment
        """
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

    def test_automation_comment_deleted_deletes_note(self, mocked_sg):
        """
        Check that the FPTR Note associated to the Jira comment is deleted.

        Test environment:
        - the sync deletion direction is set to "both_way"
        - the comment no longer exists in Jira
        Expected result:
        - the Note is deleted, though Jira cannot be asked about the comment
        """
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

        jira_comment.delete()

        payload = automation_body(event_type="comment_deleted", id=jira_comment.id)
        self.assertTrue(self._sync(bridge, jira_issue, payload, name=name))

        self.assertEqual(
            bridge.shotgun.find("Note", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_id]]), []
        )

    def test_automation_comment_deleted_deletion_sync_disabled_rejected(
        self, mocked_sg
    ):
        """
        Check that a deletion is ignored when it is not enabled in the settings.

        Expected result:
        - the event is rejected
        """
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)
        jira_comment = bridge.jira.add_comment(jira_issue, body="x", author=HUMAN_USER)
        jira_comment.delete()

        payload = automation_body(event_type="comment_deleted", id=jira_comment.id)

        self.assertFalse(self._sync(bridge, jira_issue, payload))

    def test_automation_comment_created_by_jira_bridge_user_rejected(self, mocked_sg):
        """
        Check that the author of a comment cannot be forged by the rule.

        Test environment:
        - the comment was made by the bridge, but the rule says a person did
        Expected result:
        - the author is read from Jira, so the event is rejected
        - no Note is created
        """
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

    def test_automation_comment_event_carries_body_and_author(self, mocked_sg):
        """
        Check that a comment event has what the handler reads in a webhook one.

        Expected result:
        - the keys of the webhook fixtures are all there
        - the body, which reply sync reads from the event, is the one in Jira
        - the author is the one in Jira
        """
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

        webhook = mock_jira.COMMENT_PAYLOAD
        self.assertTrue(set(webhook["comment"]) <= set(event["comment"]))
        self.assertTrue(set(webhook["issue"]) <= set(event["issue"]))
        self.assertEqual(event["comment"]["body"], "a comment")
        self.assertEqual(
            event["comment"]["author"]["accountId"], HUMAN_USER["accountId"]
        )

    # -------------------------------------------------------------------------------
    # Worklog
    # -------------------------------------------------------------------------------

    def test_automation_worklog_created_creates_timelog(self, mocked_sg):
        """
        Check that the FPTR TimeLog associated to the Jira worklog is created.

        Expected result:
        - one TimeLog is created, linked to the worklog
        """
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

    def test_automation_worklog_updated_updates_timelog(self, mocked_sg):
        """
        Check that the FPTR TimeLog associated to the Jira worklog is updated.

        Expected result:
        - the duration of the TimeLog is the time spent, in minutes
        """
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

    def test_automation_worklog_deleted_deletes_timelog(self, mocked_sg):
        """
        Check that the FPTR TimeLog associated to the Jira worklog is deleted.

        Test environment:
        - the sync deletion direction is set to "both_way"
        - the worklog no longer exists in Jira
        Expected result:
        - the TimeLog is deleted, though Jira cannot be asked about the worklog
        """
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

        jira_worklog.delete()

        payload = automation_body(event_type="worklog_deleted", id=jira_worklog.id)
        self.assertTrue(self._sync(bridge, jira_issue, payload, name=name))

        self.assertEqual(
            bridge.shotgun.find("TimeLog", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_id]]),
            [],
        )

    def test_automation_worklog_created_by_jira_bridge_user_rejected(self, mocked_sg):
        """
        Check that the author of a worklog cannot be forged by the rule.

        Expected result:
        - the worklog was made by the bridge, so the event is rejected
        """
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(
            jira_issue, timeSpentSeconds=0, author=BRIDGE_USER
        )
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        payload = automation_body(event_type="worklog_created", id=jira_worklog.id)

        self.assertFalse(self._sync(bridge, jira_issue, payload))

    def test_automation_worklog_timelog_not_configured_rejected(self, mocked_sg):
        """
        Check that a worklog is ignored when TimeLog is not mapped in the settings.

        Test environment:
        - the settings have no entry for the FPTR TimeLog entity
        Expected result:
        - the event is rejected, and the log says why
        - no TimeLog is created
        """
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

    # -------------------------------------------------------------------------------
    # Bad requests
    # -------------------------------------------------------------------------------

    def test_automation_issue_unknown_rejected(self, mocked_sg):
        """Check that an Issue which does not exist is refused as a bad request."""
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        with self.assertRaisesRegex(JiraAutomationPayloadError, "NOPE-1"):
            normalize_automation_request(
                automation_body(), "Issue", "NOPE-1", bridge.jira
            )

    def test_automation_comment_unknown_rejected(self, mocked_sg):
        """Check that a comment which does not exist is refused as a bad request."""
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)

        payload = automation_body(event_type="comment_created", id="999")

        with self.assertRaisesRegex(JiraAutomationPayloadError, "was not found"):
            self._sync(bridge, jira_issue, payload)

    def test_automation_worklog_unknown_rejected(self, mocked_sg):
        """Check that a worklog which does not exist is refused as a bad request."""
        bridge, jira_issue, _ = self._issue_with_task(mocked_sg)

        payload = automation_body(event_type="worklog_updated", id="999")

        with self.assertRaisesRegex(JiraAutomationPayloadError, "was not found"):
            self._sync(bridge, jira_issue, payload)


@mock.patch("shotgun_api3.Shotgun")
class TestAutomationReplyParity(TestSyncBase):
    """Automation requests for comment replies behave like the webhook ones."""

    HANDLER_NAME = "entities_generic_with_reply"

    # Reuse the fixtures of the reply tests, without running their tests again.
    _get_syncer = reply_tests.TestReplySync._get_syncer
    _mock_jira_data = reply_tests.TestReplySync._mock_jira_data
    _setup_common_sg_data = reply_tests.TestReplySync._setup_common_sg_data
    _setup_sg_task = reply_tests.TestReplySync._setup_sg_task
    _setup_sg_note = reply_tests.TestReplySync._setup_sg_note

    def _reply_scenario(self, bridge, body="new reply text", reply_synced=False):
        """
        Return a synced Issue, a reply made by a person and its parent FPTR Note.

        :param bool reply_synced: If True, the reply is already synced: its FPTR
            Reply exists and the Note maps it to the Jira reply.
        :returns: A tuple (Jira Issue, Jira reply, FPTR Note, FPTR Reply or None).
        """
        self._setup_common_sg_data(bridge)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        created = bridge.jira.add_comment_reply(jira_issue.key, jira_comment.id, body)
        # The Jira mock keeps its own copy of the reply, the one to update.
        jira_reply = bridge.jira.comment(jira_issue.key, created.id)
        # Replies are made by people, not by the bridge.
        jira_reply.update(author={"accountId": HUMAN_USER["accountId"]})
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_reply = None
        mapping = None
        if reply_synced:
            sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
            self.add_to_sg_mock_db(bridge.shotgun, sg_reply)
            mapping = {str(sg_reply["id"]): jira_reply.id}
        sg_note = self._setup_sg_note(
            bridge, sg_task, jira_issue, jira_comment, reply_mapping=mapping
        )
        return jira_issue, jira_reply, sg_note, sg_reply

    def _normalize(self, bridge, jira_issue, **fields):
        """Return the event for a rule which sends ``fields``."""
        return normalize_automation_request(
            automation_body(**fields), "Issue", jira_issue.key, bridge.jira
        )

    def test_automation_reply_created_creates_fptr_reply(self, mocked_sg):
        """
        Check that a comment reply made in Jira is created as a FPTR Reply.

        Test environment:
        - Reply syncing is enabled on the Note entity
        - the parent comment is already synced as a Note
        Expected result:
        - one Reply is created on the Note, with the text of the reply
        - the Note maps the Reply to the Jira reply
        """
        syncer, bridge = self._get_syncer(mocked_sg)
        jira_issue, jira_reply, sg_note, _ = self._reply_scenario(bridge)

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

    def test_automation_reply_event_carries_parent_and_body(self, mocked_sg):
        """
        Check that a reply event has what reply sync reads in a webhook one.

        Expected result:
        - the parent of the reply and its body are both in the event
        """
        syncer, bridge = self._get_syncer(mocked_sg)
        jira_issue, jira_reply, _, _ = self._reply_scenario(bridge)

        event = self._normalize(
            bridge, jira_issue, event_type="comment_created", id=jira_reply.id
        )

        self.assertEqual(event["comment"]["parentId"], jira_reply.parentId)
        self.assertEqual(event["comment"]["body"], "new reply text")

    def test_automation_reply_deleted_not_recognized_as_reply(self, mocked_sg):
        """
        Document the known limitation for deleted replies.

        Jira cannot be asked about a deleted comment, so the event has no
        ``parentId``, which a site webhook carries. Reply sync routes on it, so the
        deletion is handled as the one of a top-level comment.

        Test environment:
        - the reply is synced: its FPTR Reply exists and the Note maps it
        - the reply no longer exists in Jira
        Expected result:
        - the event has no ``parentId``
        - the FPTR Reply and the mapping of the Note are left as they were
        - the Note of the parent comment is left alone as well
        """
        syncer, bridge = self._get_syncer(mocked_sg)
        jira_issue, jira_reply, sg_note, sg_reply = self._reply_scenario(
            bridge, reply_synced=True
        )
        jira_reply.delete()

        event = self._normalize(
            bridge, jira_issue, event_type="comment_deleted", id=jira_reply.id
        )
        bridge.sync_in_shotgun(self.HANDLER_NAME, "issue", jira_issue.key, event)

        self.assertNotIn("parentId", event["comment"])
        self.assertEqual(
            [
                reply["id"]
                for reply in bridge.shotgun.find(
                    "Reply", [["entity", "is", {"type": "Note", "id": sg_note["id"]}]]
                )
            ],
            [sg_reply["id"]],
        )
        note = bridge.shotgun.find_one(
            "Note", [["id", "is", sg_note["id"]]], [SHOTGUN_JIRA_REPLY_IDS_FIELD]
        )
        self.assertEqual(
            json.loads(note[SHOTGUN_JIRA_REPLY_IDS_FIELD]),
            {str(sg_reply["id"]): jira_reply.id},
        )

    def test_automation_comment_deleted_with_replies_deletes_note(self, mocked_sg):
        """
        Check that a deleted comment which has replies is still handled as a Note.

        Expected result:
        - the Note of the comment is deleted
        """
        syncer, bridge = self._get_syncer(mocked_sg)
        jira_issue, jira_reply, sg_note, _ = self._reply_scenario(
            bridge, reply_synced=True
        )
        parent_id = sg_note[SHOTGUN_JIRA_ID_FIELD].split("/")[1]
        bridge.jira.comment(jira_issue.key, parent_id).delete()

        event = self._normalize(
            bridge, jira_issue, event_type="comment_deleted", id=parent_id
        )
        self.assertTrue(
            bridge.sync_in_shotgun(self.HANDLER_NAME, "issue", jira_issue.key, event)
        )

        self.assertEqual(bridge.shotgun.find("Note", [["id", "is", sg_note["id"]]]), [])

    def test_automation_reply_deleted_unknown_to_fptr_does_not_fail(self, mocked_sg):
        """
        Check that a deleted comment which FPTR has no trace of is not an error.

        Test environment:
        - the reply was never synced, so no Note maps it
        Expected result:
        - the event is handled as the deletion of a Note, which finds nothing
        - the Note of the parent comment is left alone
        """
        syncer, bridge = self._get_syncer(mocked_sg)
        jira_issue, jira_reply, sg_note, _ = self._reply_scenario(bridge)
        jira_reply.delete()

        event = self._normalize(
            bridge, jira_issue, event_type="comment_deleted", id=jira_reply.id
        )

        bridge.sync_in_shotgun(self.HANDLER_NAME, "issue", jira_issue.key, event)

        self.assertEqual(
            len(bridge.shotgun.find("Note", [["id", "is", sg_note["id"]]])), 1
        )
