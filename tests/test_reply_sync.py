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
        new_reply = all_comments[-1]
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
        sg_reply["content"] = "[mention:%s:FordPrefect] thanks" % mock_shotgun.SG_USER["id"]
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
        updated_mapping = json.loads(
            updated_note[SHOTGUN_JIRA_REPLY_IDS_FIELD] or "{}"
        )
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

    def test_jira_reply_accepted(self, mocked_sg):
        """A comment_created event with parentId should be accepted and processed."""
        syncer, bridge = self._get_syncer(mocked_sg)
        self._setup_common_sg_data(bridge)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "parent comment")
        jira_reply = bridge.jira.add_comment_reply(
            jira_issue.key, jira_comment.id, "reply"
        )
        sg_task = self._setup_sg_task(bridge, jira_issue)
        self._setup_sg_note(bridge, sg_task, jira_issue, jira_comment)

        event = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": jira_reply.id,
                "parentId": int(jira_comment.id),
                "body": "reply",
                "author": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
                "updateAuthor": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            },
            "issue": {"id": jira_issue.key, "key": jira_issue.key},
        }

        self.assertTrue(
            bridge.sync_in_shotgun(self.HANDLER_NAME, "issue", jira_issue.key, event)
        )

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
                "body": "[~accountid:%s] fyi" % mock_shotgun.SG_USER["sg_jira_account_id"],
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

        expected_placeholders = "[mention:%s:FordPrefect] and [mention:%s:SyncSync] please review" % (
            mock_shotgun.SG_USER["id"],
            mock_shotgun.SG_USER_2["id"],
        )
        replies = bridge.shotgun.find(
            "Reply",
            [["entity", "is", {"type": "Note", "id": sg_note["id"]}]],
            ["content"],
        )
        self.assertEqual(len(replies), 1)
        sg_reply = replies[0]
        self.assertEqual(sg_reply["content"], expected_placeholders)

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
