# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
import copy
import json
import os
import unittest.mock as mock

import jira
import mock_jira
import mock_shotgun
from shotgun_api3.lib import mockgun
from test_sync_base import TestSyncBase

import sg_jira
from sg_jira.constants import (
    JIRA_SHOTGUN_ID_FIELD,
    JIRA_SHOTGUN_TYPE_FIELD,
    JIRA_SYNC_IN_FPTR_FIELD,
    SHOTGUN_JIRA_ID_FIELD,
    SHOTGUN_JIRA_REPLY_IDS_FIELD,
    SHOTGUN_SYNC_IN_JIRA_FIELD,
)


@mock.patch("shotgun_api3.Shotgun")
class TestReplySync(TestSyncBase):
    """Test bidirectional sync of FPTR Reply entities via Jira comment replies."""

    HANDLER_NAME = "entities_generic_with_reply"

    def _get_syncer(self, mocked_sg, name="entities_generic_with_reply"):
        """
        Override to inject sg_jira_reply_ids into Note's schema and
        ensure Reply entity type is present in the schema.
        """
        sg = mockgun.Shotgun("https://mocked.my.com", "Ford Prefect", "xxxxxxxxxx")

        for sg_field in [SHOTGUN_SYNC_IN_JIRA_FIELD, SHOTGUN_JIRA_ID_FIELD]:
            new_field = copy.deepcopy(sg._schema["Task"][sg_field])
            new_field["entity_type"]["value"] = "Asset"
            sg._schema["Asset"][sg_field] = new_field

        reply_ids_field = copy.deepcopy(sg._schema["Note"][SHOTGUN_JIRA_ID_FIELD])
        reply_ids_field["unique"] = {"value": False, "editable": False}
        sg._schema["Note"][SHOTGUN_JIRA_REPLY_IDS_FIELD] = reply_ids_field

        if "Reply" not in sg._schema_entity:
            sg._schema_entity["Reply"] = copy.deepcopy(sg._schema_entity["Note"])
        # Copy Note's schema so mockgun validates field names/types on Reply create/update/find.
        # Also initialize _db["Reply"] since mockgun only creates _db entries from _schema at init time.
        if "Reply" not in sg._schema:
            sg._schema["Reply"] = copy.deepcopy(sg._schema["Note"])
        # Reply needs an "entity" field (entity link to Note) that Note itself doesn't have.
        # Use "user" as a template since it's also an entity-type field.
        if "entity" not in sg._schema["Reply"]:
            entity_field = copy.deepcopy(sg._schema["Reply"]["user"])
            sg._schema["Reply"]["entity"] = entity_field
        if "Reply" not in sg._db:
            sg._db["Reply"] = {}

        mocked_sg.return_value = sg
        bridge = sg_jira.Bridge.get_bridge(
            os.path.join(self._fixtures_path, "settings.py")
        )
        syncer = bridge.get_syncer(name)
        return syncer, bridge

    def _mock_jira_data(self, bridge, sg_entity=None, sync_in_fptr="True"):
        """Helper: create a Jira issue with required fields."""
        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        if sg_entity:
            return bridge.jira.create_issue(
                {
                    "issuetype": bridge.jira.issue_type_by_name("Task"),
                    bridge.jira.get_jira_issue_field_id(
                        JIRA_SHOTGUN_ID_FIELD.lower()
                    ): sg_entity["id"],
                    bridge.jira.get_jira_issue_field_id(
                        JIRA_SHOTGUN_TYPE_FIELD.lower()
                    ): sg_entity["type"],
                    bridge.jira.get_jira_issue_field_id(
                        JIRA_SYNC_IN_FPTR_FIELD.lower()
                    ): jira.resources.CustomFieldOption(
                        None, None, {"value": sync_in_fptr}
                    ),
                }
            )
        return bridge.jira.create_issue(
            fields={
                "issuetype": bridge.jira.issue_type_by_name("Task"),
                bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_ID_FIELD.lower()): "",
                bridge.jira.get_jira_issue_field_id(
                    JIRA_SHOTGUN_TYPE_FIELD.lower()
                ): "",
                bridge.jira.get_jira_issue_field_id(
                    JIRA_SYNC_IN_FPTR_FIELD.lower()
                ): jira.resources.CustomFieldOption(
                    None, None, {"value": sync_in_fptr}
                ),
            }
        )

    def _setup_common_sg_data(self, bridge):
        """Add common SG project and user entities to the mock DB."""
        self.add_to_sg_mock_db(bridge.shotgun, mock_shotgun.SG_PROJECT)
        self.add_to_sg_mock_db(bridge.shotgun, mock_shotgun.SG_USER)
        self.add_to_sg_mock_db(bridge.shotgun, mock_shotgun.SG_USER_2)

    def _setup_sg_task(self, bridge, jira_issue):
        """Create and store a FPTR Task linked to the Jira issue."""
        sg_task = copy.deepcopy(mock_shotgun.SG_TASK)
        sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True
        sg_task[SHOTGUN_JIRA_ID_FIELD] = jira_issue.key
        self.add_to_sg_mock_db(bridge.shotgun, sg_task)
        return sg_task

    def _setup_sg_note(
        self, bridge, sg_task, jira_issue, jira_comment, reply_mapping=None
    ):
        """Create and store a FPTR Note linked to the Jira comment."""
        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note["tasks"] = [sg_task]
        sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_comment.id)
        sg_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] = (
            json.dumps(reply_mapping) if reply_mapping else ""
        )
        self.add_to_sg_mock_db(bridge.shotgun, sg_note)
        return sg_note

    # ---------------------------------------------------------------------------
    # FPTR Reply → Jira
    # ---------------------------------------------------------------------------

    def test_fptr_reply_parent_note_not_synced_rejected(self, mocked_sg):
        """A Reply event must be rejected when the parent Note has no Jira key."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note[SHOTGUN_JIRA_ID_FIELD] = ""
        sg_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] = ""
        self.add_to_sg_mock_db(bridge.shotgun, sg_note)

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Reply",
                sg_reply["id"],
                mock_shotgun.SG_REPLY_CHANGE_EVENT,
            )
        )

    def test_fptr_reply_rejected_when_parent_note_jira_key_invalid(self, mocked_sg):
        """A Reply event must be rejected when the parent Note has a malformed Jira key."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note["tasks"] = [sg_task]
        sg_note[SHOTGUN_JIRA_ID_FIELD] = "FAKED-01"
        self.add_to_sg_mock_db(bridge.shotgun, sg_note)

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Reply",
                sg_reply["id"],
                mock_shotgun.SG_REPLY_CHANGE_EVENT,
            )
        )
        self.assertEqual(
            len(
                [
                    c
                    for c in bridge.jira.comments(jira_issue.key)
                    if c.raw.get("parentId")
                ]
            ),
            0,
        )

    def test_fptr_reply_create_failure_when_jira_rejects_reply(self, mocked_sg):
        """Sync must fail when Jira refuses to create the comment reply."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        with mock.patch.object(bridge.jira, "add_comment_reply", return_value=None):
            self.assertFalse(
                bridge.sync_in_jira(
                    self.HANDLER_NAME,
                    "Reply",
                    sg_reply["id"],
                    mock_shotgun.SG_REPLY_CHANGE_EVENT,
                )
            )

    def test_fptr_reply_creates_jira_reply(self, mocked_sg):
        """Creating a FPTR Reply should create a Jira comment reply and update the Note's mapping."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        initial_count = len(bridge.jira.comments(jira_issue.key))

        result = bridge.sync_in_jira(
            self.HANDLER_NAME,
            "Reply",
            sg_reply["id"],
            mock_shotgun.SG_REPLY_CHANGE_EVENT,
        )

        self.assertTrue(result)
        all_comments = bridge.jira.comments(jira_issue.key)
        self.assertEqual(len(all_comments), initial_count + 1)
        new_reply = next(c for c in all_comments if c.raw.get("parentId"))
        self.assertIsNotNone(new_reply.raw.get("parentId"))

        updated_note = bridge.shotgun.find_one(
            "Note", [["id", "is", sg_note["id"]]], [SHOTGUN_JIRA_REPLY_IDS_FIELD]
        )
        mapping = json.loads(updated_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] or "{}")
        self.assertIn(str(sg_reply["id"]), mapping)

    def test_fptr_reply_mention_placeholder_rewritten_to_jira_mention(self, mocked_sg):
        """A FPTR mention placeholder in a Reply's content should become a Jira mention."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        sg_reply["content"] = (
            "[mention:%s:FordPrefect] thanks" % mock_shotgun.SG_USER["id"]
        )
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        result = bridge.sync_in_jira(
            self.HANDLER_NAME,
            "Reply",
            sg_reply["id"],
            mock_shotgun.SG_REPLY_CHANGE_EVENT,
        )

        self.assertTrue(result)
        new_reply = bridge.jira.comments(jira_issue.key)[-1]
        self.assertIn(
            "[~accountid:%s]" % mock_shotgun.SG_USER["sg_jira_account_id"],
            new_reply.body,
        )

    def test_fptr_reply_updates_jira_reply(self, mocked_sg):
        """Editing a FPTR Reply body should update the corresponding Jira comment reply."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, "old reply body"
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)

        mapping = {str(mock_shotgun.SG_REPLY["id"]): jira_reply.id}
        sg_note = self._setup_sg_note(
            bridge, sg_task, jira_issue, jira_comment, reply_mapping=mapping
        )

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["content"] = "updated reply content"
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        result = bridge.sync_in_jira(
            self.HANDLER_NAME,
            "Reply",
            sg_reply["id"],
            mock_shotgun.SG_REPLY_CHANGE_EVENT,
        )

        self.assertTrue(result)
        updated_jira_reply = bridge.jira.comment(jira_issue.key, jira_reply.id)
        self.assertIn("updated reply content", updated_jira_reply.body)

    def test_fptr_reply_delete_removes_jira_reply(self, mocked_sg):
        """Deleting a FPTR Reply should remove the Jira reply and clean the mapping."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, "reply body"
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)

        mapping = {str(mock_shotgun.SG_REPLY["id"]): jira_reply.id}
        sg_note = self._setup_sg_note(
            bridge, sg_task, jira_issue, jira_comment, reply_mapping=mapping
        )

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        sg_reply["retirement_date"] = "2025-01-01T00:00:00Z"
        sg_reply["__retired"] = True
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        delete_event = copy.deepcopy(mock_shotgun.SG_REPLY_CHANGE_EVENT)
        delete_event["meta"]["attribute_name"] = "retirement_date"

        initial_count = len(bridge.jira.comments(jira_issue.key))

        result = bridge.sync_in_jira(
            self.HANDLER_NAME,
            "Reply",
            sg_reply["id"],
            delete_event,
        )

        self.assertTrue(result)
        self.assertEqual(len(bridge.jira.comments(jira_issue.key)), initial_count - 1)

        updated_note = bridge.shotgun.find_one(
            "Note", [["id", "is", sg_note["id"]]], [SHOTGUN_JIRA_REPLY_IDS_FIELD]
        )
        updated_mapping = json.loads(updated_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] or "{}")
        self.assertNotIn(str(sg_reply["id"]), updated_mapping)

    def test_fptr_reply_delete_rejected_if_not_in_mapping(self, mocked_sg):
        """A deletion event for a Reply with no mapping entry must be rejected."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        sg_reply["retirement_date"] = "2025-01-01T00:00:00Z"
        sg_reply["__retired"] = True
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        delete_event = copy.deepcopy(mock_shotgun.SG_REPLY_CHANGE_EVENT)
        delete_event["meta"]["attribute_name"] = "retirement_date"

        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Reply",
                sg_reply["id"],
                delete_event,
            )
        )

    # ---------------------------------------------------------------------------
    # Jira Reply → FPTR
    # ---------------------------------------------------------------------------

    def test_jira_reply_creates_fptr_reply(self, mocked_sg):
        """A comment_created with parentId should create a FPTR Reply."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, "new reply text"
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        event = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": "new reply text",
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }

        result = bridge.sync_in_shotgun(
            self.HANDLER_NAME, "issue", jira_issue.key, event
        )
        self.assertTrue(result)

        replies = bridge.shotgun.find(
            "Reply",
            [["entity", "is", {"type": "Note", "id": sg_note["id"]}]],
            ["content", "entity"],
        )
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["content"], "new reply text")

        updated_note = bridge.shotgun.find_one(
            "Note", [["id", "is", sg_note["id"]]], [SHOTGUN_JIRA_REPLY_IDS_FIELD]
        )
        mapping = json.loads(updated_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] or "{}")
        self.assertIn(str(replies[0]["id"]), mapping)

    def test_jira_reply_mention_rewritten_to_fptr_placeholder(self, mocked_sg):
        """A Jira mention in a reply body should become a readable FPTR placeholder."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key,
            jira_comment.id,
            "[~accountid:%s] fyi" % mock_shotgun.SG_USER["sg_jira_account_id"],
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        event = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": "[~accountid:%s] fyi"
                % mock_shotgun.SG_USER["sg_jira_account_id"],
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }

        result = bridge.sync_in_shotgun(
            self.HANDLER_NAME, "issue", jira_issue.key, event
        )
        self.assertTrue(result)

        replies = bridge.shotgun.find(
            "Reply",
            [["entity", "is", {"type": "Note", "id": sg_note["id"]}]],
            ["content"],
        )
        self.assertEqual(len(replies), 1)
        self.assertEqual(
            replies[0]["content"],
            "[mention:%s:FordPrefect] fyi" % mock_shotgun.SG_USER["id"],
        )

    def test_multiple_mentions_round_trip_jira_to_fptr_and_back(self, mocked_sg):
        """
        A Jira reply mentioning two mapped users should sync to FPTR with both
        rewritten to their own placeholder, and editing that FPTR Reply should
        sync back to Jira with both placeholders restored to real mentions.
        """
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        account_id_1 = mock_shotgun.SG_USER["sg_jira_account_id"]
        account_id_2 = mock_shotgun.SG_USER_2["sg_jira_account_id"]
        original_body = "[~accountid:%s] and [~accountid:%s] please review" % (
            account_id_1,
            account_id_2,
        )
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, original_body
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        # Jira -> FPTR: both mentions should become their own placeholder.
        event = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": original_body,
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }
        self.assertTrue(
            bridge.sync_in_shotgun(self.HANDLER_NAME, "issue", jira_issue.key, event)
        )

        expected_placeholders = (
            "[mention:%s:FordPrefect] and [mention:%s:SyncSync] please review"
            % (
                mock_shotgun.SG_USER["id"],
                mock_shotgun.SG_USER_2["id"],
            )
        )
        replies = bridge.shotgun.find(
            "Reply",
            [["entity", "is", {"type": "Note", "id": sg_note["id"]}]],
            ["content"],
        )
        self.assertEqual(len(replies), 1)
        sg_reply = replies[0]
        self.assertEqual(sg_reply["content"], expected_placeholders)

        # mockgun (unlike real Shotgun) doesn't resolve a "name" on entity-link
        # fields read back after create() - patch the DB directly so the
        # FPTR -> Jira half below has a realistic "user" to build the reply
        # comment's byline from.
        bridge.shotgun._db["Reply"][sg_reply["id"]]["user"] = {
            "type": "HumanUser",
            "id": mock_shotgun.SG_USER_2["id"],
            "name": mock_shotgun.SG_USER_2["name"],
        }

        # FPTR -> Jira: editing the Reply should restore both real mentions.
        edited_content = expected_placeholders.replace(
            "please review", "please review, thanks"
        )
        bridge.shotgun.update("Reply", sg_reply["id"], {"content": edited_content})

        result = bridge.sync_in_jira(
            self.HANDLER_NAME,
            "Reply",
            sg_reply["id"],
            mock_shotgun.SG_REPLY_CHANGE_EVENT,
        )
        self.assertTrue(result)

        updated_jira_reply = bridge.jira.comment(jira_issue.key, jira_reply.id)
        self.assertIn(
            "[~accountid:%s] and [~accountid:%s] please review, thanks"
            % (account_id_1, account_id_2),
            updated_jira_reply.body,
        )

    def test_jira_reply_edit_does_not_leak_fptr_wrapper_into_content(self, mocked_sg):
        """
        Editing an FPTR-originated Jira reply through the Jira UI wraps it in
        a `{panel:bgColor=...}` block with a "_Reply created from FPTR by
        X_" byline (confirmed against a live Jira Cloud site). Syncing that
        edit back to FPTR must strip the wrapper, not leak it into the Reply's
        content - matching how Note edits already behave.
        """
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, "original reply"
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        mapping = {str(sg_reply["id"]): jira_reply.id}
        self._setup_sg_note(
            bridge, sg_task, jira_issue, jira_comment, reply_mapping=mapping
        )

        edited_body = (
            "{panel:bgColor=#deebff}\n"
            "_Reply created from FPTR by Ford Prefect_\n"
            "edited via Jira UI\n"
            "{panel}"
        )
        event = {
            "webhookEvent": "comment_updated",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": edited_body,
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }

        result = bridge.sync_in_shotgun(
            self.HANDLER_NAME, "issue", jira_issue.key, event
        )
        self.assertTrue(result)

        sg_reply = bridge.shotgun.find_one(
            "Reply", [["id", "is", mock_shotgun.SG_REPLY["id"]]], ["content", "user"]
        )
        self.assertEqual(sg_reply["content"], "edited via Jira UI")
        self.assertNotIn("panel", sg_reply["content"])
        self.assertNotIn("Reply created from FPTR", sg_reply["content"])
        # The embedded byline should also resolve the correct FPTR author.
        self.assertEqual(sg_reply["user"]["id"], mock_shotgun.SG_USER["id"])

    def test_jira_reply_deletes_fptr_reply(self, mocked_sg):
        """A comment_deleted with parentId should delete the FPTR Reply."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, "reply to delete"
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        mapping = {str(sg_reply["id"]): jira_reply.id}
        sg_note = self._setup_sg_note(
            bridge, sg_task, jira_issue, jira_comment, reply_mapping=mapping
        )

        event = {
            "webhookEvent": "comment_deleted",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": "reply to delete",
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }

        result = bridge.sync_in_shotgun(
            self.HANDLER_NAME, "issue", jira_issue.key, event
        )
        self.assertTrue(result)

        remaining = bridge.shotgun.find(
            "Reply",
            [["entity", "is", {"type": "Note", "id": sg_note["id"]}]],
        )
        self.assertEqual(len(remaining), 0)

    def test_regular_comment_creates_note_not_reply(self, mocked_sg):
        """A comment_created event without parentId should create a Note, not a Reply."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._setup_sg_task(bridge, jira_issue)
        jira_comment = bridge.jira.add_comment(jira_issue, "top-level comment")

        event = copy.deepcopy(mock_jira.COMMENT_PAYLOAD)
        event["comment"]["id"] = jira_comment.id
        event["comment"]["author"] = {"accountId": mock_jira.JIRA_USER_2["accountId"]}
        event["issue"]["key"] = jira_issue.key
        event["issue"]["id"] = jira_issue.key

        result = bridge.sync_in_shotgun(
            self.HANDLER_NAME, "issue", jira_issue.key, event
        )
        self.assertTrue(result)

        notes = bridge.shotgun.find("Note", [])
        self.assertGreater(len(notes), 0)
        replies = bridge.shotgun.find("Reply", [])
        self.assertEqual(len(replies), 0)

    # ---------------------------------------------------------------------------
    # Rejecting Jira comment/reply events for unconfigured entity types
    # ---------------------------------------------------------------------------

    def test_jira_comment_rejected_when_note_not_configured(self, mocked_sg):
        """
        A live comment_created webhook must be rejected (not create a bare
        Note) when Note isn't present in entity_mapping - matching how
        accept_shotgun_event already rejects unconfigured FPTR entity types
        for the FPTR -> Jira direction.
        """
        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_without_note"
        )
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = copy.deepcopy(mock_shotgun.SG_TASK)
        sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True
        sg_task[SHOTGUN_JIRA_ID_FIELD] = jira_issue.key
        self.add_to_sg_mock_db(bridge.shotgun, sg_task)

        jira_comment = bridge.jira.add_comment(jira_issue, "new comment")

        event = copy.deepcopy(mock_jira.COMMENT_PAYLOAD)
        event["comment"]["id"] = jira_comment.id
        event["comment"]["author"] = {"accountId": mock_jira.JIRA_USER_2["accountId"]}
        event["issue"]["key"] = jira_issue.key
        event["issue"]["id"] = jira_issue.key

        result = bridge.sync_in_shotgun(
            "entities_generic_without_note", "issue", jira_issue.key, event
        )
        self.assertFalse(result)
        self.assertEqual(bridge.shotgun.find("Note", []), [])

    def test_jira_reply_rejected_when_reply_not_configured(self, mocked_sg):
        """
        A live comment_created webhook for a reply (parentId set) must be
        rejected when Reply isn't present in entity_mapping.
        """
        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_without_note"
        )
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = copy.deepcopy(mock_shotgun.SG_TASK)
        sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True
        sg_task[SHOTGUN_JIRA_ID_FIELD] = jira_issue.key
        self.add_to_sg_mock_db(bridge.shotgun, sg_task)

        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, "a reply"
        )

        event = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": "a reply",
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }

        result = bridge.sync_in_shotgun(
            "entities_generic_without_note", "issue", jira_issue.key, event
        )
        self.assertFalse(result)
        self.assertEqual(bridge.shotgun.find("Reply", []), [])

    # ---------------------------------------------------------------------------
    # Backfilling existing Notes/Replies when a Task is synced for the first time
    # ---------------------------------------------------------------------------

    def test_fptr_task_sync_backfills_existing_note_and_reply(self, mocked_sg):
        """
        Flagging an already-Jira-linked Task as synced should backfill not just
        pre-existing Notes but also pre-existing Replies on those Notes.
        """
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._setup_sg_task(bridge, jira_issue)

        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note["tasks"] = [sg_task]
        sg_note[SHOTGUN_JIRA_ID_FIELD] = ""
        sg_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] = ""
        self.add_to_sg_mock_db(bridge.shotgun, sg_note)

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        sync_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sync_event["meta"]["attribute_name"] = SHOTGUN_SYNC_IN_JIRA_FIELD

        result = bridge.sync_in_jira(
            self.HANDLER_NAME, "Task", sg_task["id"], sync_event
        )
        self.assertTrue(result)

        # comments() returns top-level comments and replies together.
        jira_comments = bridge.jira.comments(jira_issue.key)
        self.assertEqual(len(jira_comments), 2)
        new_comment = next(c for c in jira_comments if not c.raw.get("parentId"))

        updated_note = bridge.shotgun.find_one(
            "Note",
            [["id", "is", sg_note["id"]]],
            [SHOTGUN_JIRA_ID_FIELD, SHOTGUN_JIRA_REPLY_IDS_FIELD],
        )
        self.assertEqual(
            updated_note[SHOTGUN_JIRA_ID_FIELD],
            "%s/%s" % (jira_issue.key, new_comment.id),
        )

        mapping = json.loads(updated_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] or "{}")
        self.assertIn(str(sg_reply["id"]), mapping)

        jira_reply_id = mapping[str(sg_reply["id"])]
        jira_reply = bridge.jira.comment(jira_issue.key, jira_reply_id)
        self.assertIsNotNone(jira_reply)
        self.assertIsNotNone(jira_reply.raw.get("parentId"))

    def test_jira_issue_sync_backfills_existing_comment_and_reply(self, mocked_sg):
        """
        Fully syncing a Jira Issue to FPTR for the first time should backfill
        not just pre-existing top-level comments but also pre-existing replies
        on those comments.
        """
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "top-level comment")
        bridge.jira.add_comment_reply(jira_issue.key, jira_comment.id, "existing reply")

        sg_task = copy.deepcopy(mock_shotgun.SG_TASK)
        sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True
        sg_task[SHOTGUN_JIRA_ID_FIELD] = jira_issue.key
        self.add_to_sg_mock_db(bridge.shotgun, sg_task)

        event = copy.deepcopy(mock_jira.ISSUE_CREATED_PAYLOAD)
        event["issue"] = {"id": jira_issue.key, "key": jira_issue.key}

        result = bridge.sync_in_shotgun(
            self.HANDLER_NAME, "issue", jira_issue.key, event
        )
        self.assertTrue(result)

        sg_note = bridge.shotgun.find_one(
            "Note",
            [
                [
                    SHOTGUN_JIRA_ID_FIELD,
                    "is",
                    "%s/%s" % (jira_issue.key, jira_comment.id),
                ]
            ],
            [SHOTGUN_JIRA_REPLY_IDS_FIELD, "subject", "content"],
        )
        self.assertIsNotNone(sg_note)
        self.assertEqual(sg_note["content"], "top-level comment")
        self.assertTrue(sg_note["subject"])

        replies = bridge.shotgun.find(
            "Reply",
            [["entity", "is", {"type": "Note", "id": sg_note["id"]}]],
            ["content"],
        )
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["content"], "existing reply")

    # ---------------------------------------------------------------------------
    # Edge cases (via bridge sync entry points)
    # ---------------------------------------------------------------------------

    def test_fptr_reply_delete_cleans_stale_mapping_when_jira_reply_gone(
        self, mocked_sg
    ):
        """Deleting a FPTR Reply clears the Note mapping even when the Jira reply is gone."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        sg_task = self._setup_sg_task(bridge, jira_issue)
        mapping = {str(mock_shotgun.SG_REPLY["id"]): "99999"}
        sg_note = self._setup_sg_note(
            bridge, sg_task, jira_issue, jira_comment, reply_mapping=mapping
        )

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        sg_reply["retirement_date"] = "2025-01-01T00:00:00Z"
        sg_reply["__retired"] = True
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        delete_event = copy.deepcopy(mock_shotgun.SG_REPLY_CHANGE_EVENT)
        delete_event["meta"]["attribute_name"] = "retirement_date"

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Reply",
                sg_reply["id"],
                delete_event,
            )
        )

        updated_note = bridge.shotgun.find_one(
            "Note",
            [["id", "is", sg_note["id"]]],
            [SHOTGUN_JIRA_REPLY_IDS_FIELD],
        )
        updated_mapping = json.loads(updated_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] or "{}")
        self.assertNotIn(str(sg_reply["id"]), updated_mapping)

    def test_fptr_reply_update_recreates_missing_jira_reply(self, mocked_sg):
        """Editing a FPTR Reply re-creates the Jira reply when the mapped comment is gone."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        sg_task = self._setup_sg_task(bridge, jira_issue)
        mapping = {str(mock_shotgun.SG_REPLY["id"]): "99999"}
        sg_note = self._setup_sg_note(
            bridge, sg_task, jira_issue, jira_comment, reply_mapping=mapping
        )

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["content"] = "updated content"
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Reply",
                sg_reply["id"],
                mock_shotgun.SG_REPLY_CHANGE_EVENT,
            )
        )

        updated_note = bridge.shotgun.find_one(
            "Note",
            [["id", "is", sg_note["id"]]],
            [SHOTGUN_JIRA_REPLY_IDS_FIELD],
        )
        new_mapping = json.loads(updated_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] or "{}")
        new_reply_id = new_mapping[str(sg_reply["id"])]
        jira_reply = bridge.jira.comment(jira_issue.key, new_reply_id)
        self.assertIn("updated content", jira_reply.body)

    def test_fptr_reply_create_succeeds_with_invalid_mapping_json_on_note(
        self, mocked_sg
    ):
        """Corrupt sg_jira_reply_ids JSON on the parent Note must not block Jira reply creation."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note["tasks"] = [sg_task]
        sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_comment.id)
        sg_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] = "not-json"
        self.add_to_sg_mock_db(bridge.shotgun, sg_note)

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Reply",
                sg_reply["id"],
                mock_shotgun.SG_REPLY_CHANGE_EVENT,
            )
        )

        updated_note = bridge.shotgun.find_one(
            "Note",
            [["id", "is", sg_note["id"]]],
            [SHOTGUN_JIRA_REPLY_IDS_FIELD],
        )
        mapping = json.loads(updated_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] or "{}")
        self.assertIn(str(sg_reply["id"]), mapping)

    def test_jira_reply_creates_fptr_reply_despite_invalid_mapping_json_on_note(
        self, mocked_sg
    ):
        """Corrupt sg_jira_reply_ids JSON on the parent Note must not block FPTR Reply creation."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, "new reply"
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note["tasks"] = [sg_task]
        sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_comment.id)
        sg_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] = "{bad json"
        self.add_to_sg_mock_db(bridge.shotgun, sg_note)

        event = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": "new reply",
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }

        self.assertTrue(
            bridge.sync_in_shotgun(self.HANDLER_NAME, "issue", jira_issue.key, event)
        )

        replies = bridge.shotgun.find(
            "Reply",
            [["entity", "is", {"type": "Note", "id": sg_note["id"]}]],
            ["content"],
        )
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["content"], "new reply")

    def test_jira_reply_skipped_when_parent_note_missing(self, mocked_sg):
        """A Jira reply webhook is rejected when no matching FPTR Note exists."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._setup_sg_task(bridge, jira_issue)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, "orphan reply"
        )

        event = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": "orphan reply",
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }

        self.assertFalse(
            bridge.sync_in_shotgun(self.HANDLER_NAME, "issue", jira_issue.key, event)
        )
        self.assertEqual(bridge.shotgun.find("Reply", []), [])

    def test_jira_reply_update_rejected_when_not_yet_synced(self, mocked_sg):
        """A Jira reply update is rejected when the Reply was never synced to FPTR."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, "edited reply"
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)
        self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        event = {
            "webhookEvent": "comment_updated",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": "edited reply",
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }

        self.assertFalse(
            bridge.sync_in_shotgun(self.HANDLER_NAME, "issue", jira_issue.key, event)
        )
        self.assertEqual(bridge.shotgun.find("Reply", []), [])

    def test_jira_reply_delete_is_noop_when_not_yet_synced(self, mocked_sg):
        """Deleting an unsynced Jira reply must not create or delete FPTR Replies."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, "gone reply"
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)
        self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        event = {
            "webhookEvent": "comment_deleted",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": "gone reply",
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }

        self.assertTrue(
            bridge.sync_in_shotgun(self.HANDLER_NAME, "issue", jira_issue.key, event)
        )
        self.assertEqual(bridge.shotgun.find("Reply", []), [])

    def test_jira_reply_unmapped_mention_preserved_in_fptr(self, mocked_sg):
        """A Jira mention with no matching FPTR user is left unchanged in the Reply content."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        body = "[~accountid:no-such-account-id] hello"
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, body
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        event = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": body,
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }

        self.assertTrue(
            bridge.sync_in_shotgun(self.HANDLER_NAME, "issue", jira_issue.key, event)
        )

        replies = bridge.shotgun.find(
            "Reply",
            [["entity", "is", {"type": "Note", "id": sg_note["id"]}]],
            ["content"],
        )
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["content"], body)

    def test_fptr_reply_unmapped_mention_placeholder_preserved_in_jira(self, mocked_sg):
        """A FPTR mention placeholder with no matching user is left unchanged in Jira."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        sg_reply = copy.deepcopy(mock_shotgun.SG_REPLY)
        sg_reply["entity"] = {"type": "Note", "id": sg_note["id"]}
        sg_reply["content"] = "[mention:999999:NoSuchUser] hello"
        self.add_to_sg_mock_db(bridge.shotgun, sg_reply)

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Reply",
                sg_reply["id"],
                mock_shotgun.SG_REPLY_CHANGE_EVENT,
            )
        )

        new_reply = next(
            c for c in bridge.jira.comments(jira_issue.key) if c.raw.get("parentId")
        )
        self.assertIn("[mention:999999:NoSuchUser] hello", new_reply.body)

    # ---------------------------------------------------------------------------
    # Comment backfill failure aggregation (patch coverage)
    #
    # These three exercise _sync_jira_comments_to_sg's partial-failure paths -
    # one comment out of several failing mid-backfill (e.g. a transient Jira/SG
    # error on a single entity). That's impractical to trigger reliably through
    # the public bridge.sync_in_shotgun entry point alone, so we mock the
    # specific internal call to force the failure, consistent with the rest of
    # this file which otherwise goes through public entry points.
    # ---------------------------------------------------------------------------

    def test_sync_jira_comments_note_entity_failure(self, mocked_sg):
        """Comment backfill reports failure when the Note entity sync fails."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)
        handler = syncer.handlers[0]

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        bridge.jira.add_comment(jira_issue, "top-level comment")
        self._setup_sg_task(bridge, jira_issue)

        with mock.patch.object(handler, "_sync_jira_entity_to_sg", return_value=False):
            self.assertFalse(handler._sync_jira_comments_to_sg(jira_issue))

    def test_sync_jira_comments_field_sync_failure(self, mocked_sg):
        """Comment backfill reports failure when field sync fails."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)
        handler = syncer.handlers[0]

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        bridge.jira.add_comment(jira_issue, "top-level comment")
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note["tasks"] = [sg_task]
        sg_note["id"] = 99

        with mock.patch.object(
            handler, "_sync_jira_entity_to_sg", return_value=sg_note
        ), mock.patch.object(handler, "_sync_jira_fields_to_sg", return_value=False):
            self.assertFalse(handler._sync_jira_comments_to_sg(jira_issue))

    def test_sync_jira_comments_reply_sync_failure(self, mocked_sg):
        """Comment backfill reports failure when reply sync fails."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)
        handler = syncer.handlers[0]

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "top-level comment")
        bridge.jira.add_comment_reply(jira_issue.key, jira_comment.id, "child reply")
        sg_task = self._setup_sg_task(bridge, jira_issue)
        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note["tasks"] = [sg_task]
        sg_note["id"] = 99

        with mock.patch.object(
            handler, "_sync_jira_entity_to_sg", return_value=sg_note
        ), mock.patch.object(
            handler, "_sync_jira_fields_to_sg", return_value=True
        ), mock.patch.object(
            handler, "_sync_jira_reply_to_sg", return_value=False
        ):
            self.assertFalse(handler._sync_jira_comments_to_sg(jira_issue))
