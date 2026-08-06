# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
import copy
import os
import sys
import unittest.mock as mock

import jira
import mock_jira
import mock_shotgun
from shotgun_api3.lib import mockgun
from test_sync_base import TestSyncBase

import sg_jira
from sg_jira.constants import (
    JIRA_EVENT_AUTOMATION_FULL_SYNC,
    JIRA_SHOTGUN_ID_FIELD,
    JIRA_SHOTGUN_TYPE_FIELD,
    JIRA_SHOTGUN_URL_FIELD,
    JIRA_SYNC_IN_FPTR_FIELD,
    SHOTGUN_JIRA_ID_FIELD,
    SHOTGUN_JIRA_URL_FIELD,
    SHOTGUN_SYNC_IN_JIRA_FIELD,
)
from sg_jira.jira_automation_payload import normalize_automation_request

# TODO:
#  - see if we can mockup the Jira Bridge schema (aka fields) to check against the field existence


class TestEntitiesGenericHandler(TestSyncBase):

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

    def _mock_sg_data(
        self, sg_instance, jira_issue=None, sync_in_jira=True, extra_fields=None
    ):
        """
        Helper method to mock FPTR data.
        We can't call it in the `setUp` method as we need the mocked_sg instance...
        """
        self.add_to_sg_mock_db(sg_instance, mock_shotgun.SG_PROJECT)
        self.add_to_sg_mock_db(sg_instance, mock_shotgun.SG_USER)

        mocked_sg_task = copy.deepcopy(mock_shotgun.SG_TASK)
        mocked_sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = sync_in_jira
        if jira_issue:
            mocked_sg_task[SHOTGUN_JIRA_ID_FIELD] = jira_issue.key
        if extra_fields:
            mocked_sg_task.update(extra_fields)
        self.add_to_sg_mock_db(sg_instance, mocked_sg_task)

        return mocked_sg_task

    def _mock_jira_data(
        self, bridge, sg_entity=None, issue_type_name="Task", sync_in_fptr="True"
    ):
        """
        Helper method to mock Jira data.
        We can't call it in the `setUp` method as we need the bridge instance...
        """
        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        if sg_entity:
            jira_issue = bridge.jira.create_issue(
                {
                    "issuetype": bridge.jira.issue_type_by_name(issue_type_name),
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
            return jira_issue
        return bridge.jira.create_issue(
            fields={
                "issuetype": bridge.jira.issue_type_by_name(issue_type_name),
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

    def _mock_jira_event(
        self, jira_issue, jira_event, jira_worklog=None, jira_comment=None
    ):
        """Helper method to mock Jira issue event."""

        mocked_jira_event = copy.deepcopy(jira_event)

        if jira_worklog:
            mocked_jira_event["worklog"]["issueId"] = jira_issue.key
            mocked_jira_event["worklog"]["id"] = jira_worklog.id
        elif jira_comment:
            mocked_jira_event["comment"]["id"] = jira_comment.id
            mocked_jira_event["issue"]["id"] = jira_issue.key
            mocked_jira_event["issue"]["key"] = jira_issue.key
        else:
            mocked_jira_event["issue"] = {"id": jira_issue.key, "key": jira_issue.key}
        return mocked_jira_event

    def _check_jira_issue(self, bridge, sg_entity, sync_in_fptr=None):
        """Helper method to check that a Jira issue is correctly created."""

        # Jira Issue should be created
        jira_issue = bridge.jira.issue(sg_entity[SHOTGUN_JIRA_ID_FIELD])
        self.assertIsNotNone(jira_issue)

        # its "Sync in FPTR" field should be set to "True"
        sync_in_fptr_jira_field_id = bridge.jira.get_jira_issue_field_id(
            JIRA_SYNC_IN_FPTR_FIELD.lower()
        )
        self.assertEqual(
            jira_issue.get_field(sync_in_fptr_jira_field_id).value, sync_in_fptr
        )

        # all its FPTR fields should be filled with the Task data
        sg_type_jira_field_id = bridge.jira.get_jira_issue_field_id(
            JIRA_SHOTGUN_TYPE_FIELD.lower()
        )
        self.assertEqual(jira_issue.get_field(sg_type_jira_field_id), sg_entity["type"])

        sg_id_jira_field_id = bridge.jira.get_jira_issue_field_id(
            JIRA_SHOTGUN_ID_FIELD.lower()
        )
        self.assertEqual(
            jira_issue.get_field(sg_id_jira_field_id), str(sg_entity["id"])
        )

        sg_url_jira_field_id = bridge.jira.get_jira_issue_field_id(
            JIRA_SHOTGUN_URL_FIELD.lower()
        )
        sg_entity_url = bridge.shotgun.get_entity_page_url(sg_entity)
        self.assertEqual(jira_issue.get_field(sg_url_jira_field_id), sg_entity_url)

        return jira_issue


# Mock Flow Production Tracking with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
class TestEntitiesGenericHandlerSettings(TestEntitiesGenericHandler):
    """Test the configuration settings for the Entities Generic Handler."""

    def test_bad_settings_formatting_for_entity_mapping(self, mocked_sg):
        """Test all the use cases where the entity mappings setting is not correctly formatted."""

        # "sg_entity" key must be defined in the entity_mapping dictionary
        self.assertRaises(
            RuntimeError,
            self._get_syncer,
            mocked_sg,
            "entities_generic_bad_sg_entity_formatting",
        )
        # "jira_issue_type" key must be defined in the entity_mapping dictionary
        self.assertRaises(
            RuntimeError,
            self._get_syncer,
            mocked_sg,
            "entities_generic_bad_jira_issue_type_formatting",
        )

    def test_bad_settings_formatting_for_field_mapping(self, mocked_sg):
        """Test all the use cases where the entity field mappings setting is not correctly formatted."""
        # "field_mapping" key must be defined in the entity_mapping dictionary
        self.assertRaises(
            RuntimeError,
            self._get_syncer,
            mocked_sg,
            "entities_generic_bad_fields_formatting",
        )
        # "sg_field" key must be defined in the field_mapping dictionary
        self.assertRaises(
            RuntimeError,
            self._get_syncer,
            mocked_sg,
            "entities_generic_bad_fields_formatting_missing_sg_field_key",
        )
        # "jira_field" key must be defined in the field_mapping dictionary
        self.assertRaises(
            RuntimeError,
            self._get_syncer,
            mocked_sg,
            "entities_generic_bad_fields_formatting_missing_jira_field_key",
        )

    def test_bad_settings_formatting_for_status_mapping(self, mocked_sg):
        """Test all the use cases where the status field mappings setting is not correctly formatted."""
        # "sg_field" key must be defined in the field_mapping dictionary
        self.assertRaises(
            RuntimeError,
            self._get_syncer,
            mocked_sg,
            "entities_generic_bad_status_formatting_missing_sg_field_key",
        )
        # "mapping" key must be defined in the field_mapping dictionary
        self.assertRaises(
            RuntimeError,
            self._get_syncer,
            mocked_sg,
            "entities_generic_bad_status_formatting_missing_mapping_key",
        )

    def test_project_in_entity_mapping(self, mocked_sg):
        """Test that a FPTR project entity cannot be used in the entity mapping."""
        self.assertRaises(
            RuntimeError, self._get_syncer, mocked_sg, "entities_generic_with_project"
        )

    def test_fptr_missing_fields_in_schema(self, mocked_sg):
        """Test that the FPTR entities used in the entity mapping are correctly setup in FPTR"""

        # SHOTGUN_JIRA_ID_FIELD field must have been created for the FPTR entity
        self.assertRaises(
            RuntimeError,
            self._get_syncer,
            mocked_sg,
            "entities_generic_sg_entity_with_missing_field_in_schema",
        )
        # FPTR field associated to Jira "assignee" field must be an entity/multi-entity field
        self.assertRaises(
            ValueError,
            self._get_syncer,
            mocked_sg,
            "entities_generic_bad_assignee_field_type",
        )
        # FPTR field associated to Jira "assignee" field must be an entity/multi-entity field supporting HumanUser
        self.assertRaises(
            ValueError,
            self._get_syncer,
            mocked_sg,
            "entities_generic_bad_assignee_field_entity_type",
        )


# Mock Flow Production Tracking with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
class TestEntitiesGenericHandlerFPTRToJira(TestEntitiesGenericHandler):
    """Test the sync from FPTR to Jira, covering for the different type of entities."""

    # -------------------------------------------------------------------------------
    # FPTR to Jira Sync - Entity Change Event (entity creation/update)
    # -------------------------------------------------------------------------------
    def test_fptr_to_jira_entity_not_supported(self, mocked_sg):
        """If an entity type is not supported (aka not defined in the settings), the event will be rejected."""
        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Shot",
                mock_shotgun.SG_SHOT["id"],
                mock_shotgun.SG_SHOT_CHANGE_EVENT,
            )
        )

    def test_fptr_to_jira_bad_sync_direction(self, mocked_sg):
        """If the sync direction is configured to only sync from Jira to FPTR, the event will be rejected."""
        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_jira_to_sg")
        self.assertFalse(
            bridge.sync_in_jira(
                "entities_generic_jira_to_sg",
                mocked_sg.SG_TASK,
                mock_shotgun.SG_TASK["id"],
                mock_shotgun.SG_TASK_CHANGE_EVENT,
            )
        )

    def test_fptr_to_jira_field_not_supported(self, mocked_sg):
        """
        If the FPTR event is about a field not supported (aka not defined in the field mapping),
        the event will be rejected.
        """

        sg_mocked_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_mocked_event["meta"]["attribute_name"] = "bad_field_name"

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Task",
                mock_shotgun.SG_TASK["id"],
                sg_mocked_event,
            )
        )

    def test_fptr_to_jira_sg_entity_not_found(self, mocked_sg):
        """If the FPTR entity associated to the event cannot be found in FPTR, the event will be rejected."""

        sg_mocked_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_mocked_event["meta"]["entity_id"] = 12345

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Task",
                sg_mocked_event["meta"]["entity_id"],
                sg_mocked_event,
            )
        )

    def test_fptr_to_jira_project_not_synced_in_jira(self, mocked_sg):
        """
        If the entity we're trying to sync doesn't belong to a FPTR already synced in Jira, the event will be rejected.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        mocked_sg_project = copy.deepcopy(mock_shotgun.SG_PROJECT)
        mocked_sg_project[SHOTGUN_JIRA_ID_FIELD] = ""

        mocked_sg_task = copy.deepcopy(mock_shotgun.SG_TASK)
        mocked_sg_task["project"] = mocked_sg_project

        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_project)
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_task)

        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Task",
                mock_shotgun.SG_TASK["id"],
                mock_shotgun.SG_TASK_CHANGE_EVENT,
            )
        )

    def test_fptr_to_jira_entity_not_flagged_as_sync(self, mocked_sg):
        """If the entity in not flagged as synced in FPTR, the event will be rejected."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg.SG_TASK)

        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Task",
                mock_shotgun.SG_TASK["id"],
                mock_shotgun.SG_TASK_CHANGE_EVENT,
            )
        )

    def test_fptr_to_jira_bad_issue_type(self, mocked_sg):
        """If the FPTR entity is mapped to a bad Jira issue type, the event will be rejected."""

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_bad_jira_issue_type"
        )

        self._mock_sg_data(bridge.shotgun)

        self.assertFalse(
            bridge.sync_in_jira(
                "entities_generic_bad_jira_issue_type",
                "Task",
                mock_shotgun.SG_TASK["id"],
                mock_shotgun.SG_TASK_CHANGE_EVENT,
            )
        )

    def test_fptr_to_jira_bad_project_jira_key(self, mocked_sg):
        """
        If the Jira key associated to the Project the entity we're trying to sync belongs to,
        doesn't refer to an existing Jira project, the event will be rejected.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        mocked_sg_project = copy.deepcopy(mock_shotgun.SG_PROJECT)
        mocked_sg_project[SHOTGUN_JIRA_ID_FIELD] = "Bad Jira Key"

        mocked_sg_task = copy.deepcopy(mock_shotgun.SG_TASK)
        mocked_sg_task["sg_project"] = mocked_sg_project
        mocked_sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True

        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_project)
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_task)

        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Task",
                mock_shotgun.SG_TASK["id"],
                mock_shotgun.SG_TASK_CHANGE_EVENT,
            )
        )

    def test_fptr_to_jira_sync_new_entity(self, mocked_sg):
        """
        When a new FPTR entity is synced to Jira, the associated Jira issue will be created.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is not set, meaning that it would be both_way by default
        - the entity doesn't exist in Jira yet
        Expected result:
        - the issue will be created in Jira
        - the Jira field "Sync in FPTR" will be set to True
        - the Jira FPTR fields will be filled
        - the FPTR JIra fields will be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        self._mock_jira_data(bridge)
        self._mock_sg_data(bridge.shotgun)

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Task",
                mock_shotgun.SG_TASK["id"],
                mock_shotgun.SG_TASK_CHANGE_EVENT,
            )
        )

        # make sure the FPTR entity has been correctly updated
        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", mock_shotgun.SG_TASK["id"]]],
            [
                SHOTGUN_JIRA_URL_FIELD,
                SHOTGUN_JIRA_ID_FIELD,
                "content",
                "sg_description",
            ],
        )
        self.assertIsNotNone(sg_task[SHOTGUN_JIRA_ID_FIELD])

        # common Jira Issue checks
        jira_issue = self._check_jira_issue(bridge, sg_task, sync_in_fptr="True")

        # Jira Issue checks specific to this use case
        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])

        self.assertIsNotNone(sg_task[SHOTGUN_JIRA_URL_FIELD])
        expected_url = {"name": "View in Jira", "url": jira_issue.permalink()}
        self.assertEqual(sg_task[SHOTGUN_JIRA_URL_FIELD], expected_url)

    def test_fptr_to_jira_sync_new_entity_both_way(self, mocked_sg):
        """
        When a new FPTR entity is synced to Jira, the associated Jira issue will be created.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is configured to work both way
        - the entity doesn't exist in Jira yet
        Expected result:
        - the issue will be created in Jira
        - the Jira field "Sync in FPTR" will be set to True
        - the Jira FPTR fields will be filled
        - the FPTR JIra fields will be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_both_way")

        self._mock_jira_data(bridge)
        self._mock_sg_data(bridge.shotgun)

        self.assertTrue(
            bridge.sync_in_jira(
                "entities_generic_both_way",
                "Task",
                mock_shotgun.SG_TASK["id"],
                mock_shotgun.SG_TASK_CHANGE_EVENT,
            )
        )

        # make sure the FPTR entity has been correctly updated
        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", mock_shotgun.SG_TASK["id"]]],
            [
                SHOTGUN_JIRA_URL_FIELD,
                SHOTGUN_JIRA_ID_FIELD,
                "content",
                "sg_description",
            ],
        )
        self.assertIsNotNone(sg_task[SHOTGUN_JIRA_ID_FIELD])

        # common Jira Issue checks
        jira_issue = self._check_jira_issue(bridge, sg_task, sync_in_fptr="True")

        # Jira Issue checks specific to this use case
        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])

        self.assertIsNotNone(sg_task[SHOTGUN_JIRA_URL_FIELD])
        expected_url = {"name": "View in Jira", "url": jira_issue.permalink()}
        self.assertEqual(sg_task[SHOTGUN_JIRA_URL_FIELD], expected_url)

    def test_fptr_to_jira_sync_new_entity_sg_to_jira_direction(self, mocked_sg):
        """
        When a new FPTR entity is synced to Jira, the associated Jira issue will be created.
        If the sync direction is set to "sg_to_jira", the Jira field "Sync in FPTR" will be set to False.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is configured to work only from FPTR to Jira
        - the entity doesn't exist in Jira yet
        Expected result:
        - the issue will be created in Jira
        - the Jira field "Sync in FPTR" will be set to False
        - the Jira FPTR fields will be filled
        - the FPTR JIra fields will be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_sg_to_jira")

        self._mock_jira_data(bridge)
        self._mock_sg_data(bridge.shotgun)

        self.assertTrue(
            bridge.sync_in_jira(
                "entities_generic_sg_to_jira",
                "Task",
                mock_shotgun.SG_TASK["id"],
                mock_shotgun.SG_TASK_CHANGE_EVENT,
            )
        )

        # make sure the FPTR entity has been correctly updated
        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", mock_shotgun.SG_TASK["id"]]],
            [
                SHOTGUN_JIRA_URL_FIELD,
                SHOTGUN_JIRA_ID_FIELD,
                "content",
                "sg_description",
            ],
        )
        self.assertIsNotNone(sg_task[SHOTGUN_JIRA_ID_FIELD])

        # common Jira Issue checks
        jira_issue = self._check_jira_issue(bridge, sg_task, sync_in_fptr="False")

        # Jira Issue checks specific to this use case
        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])

        self.assertIsNotNone(sg_task[SHOTGUN_JIRA_URL_FIELD])
        expected_url = {"name": "View in Jira", "url": jira_issue.permalink()}
        self.assertEqual(sg_task[SHOTGUN_JIRA_URL_FIELD], expected_url)

    def test_fptr_to_jira_sync_existing_entity_one_field_only(self, mocked_sg):
        """
        When a field of an entity already synced to Jira is updated in FPTR, the associated Jira Issue will be updated
        accordingly.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is configured to work both way
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - only the associated field will be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertNotEqual(jira_issue.fields.summary, mocked_sg.SG_TASK["content"])
        self.assertNotEqual(
            jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"]
        )

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Task",
                mock_shotgun.SG_TASK["id"],
                mock_shotgun.SG_TASK_CHANGE_EVENT,
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", mock_shotgun.SG_TASK["id"]]],
            [
                SHOTGUN_JIRA_URL_FIELD,
                SHOTGUN_JIRA_ID_FIELD,
                "content",
                "sg_description",
            ],
        )
        jira_issue = bridge.jira.issue(jira_issue.key)

        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        self.assertNotEqual(jira_issue.fields.description, sg_task["sg_description"])

    def test_fptr_to_jira_sync_existing_entity_all_fields(self, mocked_sg):
        """
        When the "Sync to Jira" field is checked in FPTR, a full sync of the entity is done to Jira.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is configured to work both way
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - all the fields will be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        sg_mocked_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_mocked_event["meta"]["attribute_name"] = SHOTGUN_SYNC_IN_JIRA_FIELD

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["tasks"] = [mocked_sg_task]
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["entity"] = mocked_sg_task
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        self.assertEqual(bridge._jira.comments(jira_issue.key), [])
        self.assertEqual(bridge._jira.worklogs(jira_issue.key), [])

        self.assertNotEqual(jira_issue.fields.summary, mocked_sg.SG_TASK["content"])
        self.assertNotEqual(
            jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"]
        )

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Task",
                mock_shotgun.SG_TASK["id"],
                sg_mocked_event,
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", mock_shotgun.SG_TASK["id"]]],
            [
                SHOTGUN_JIRA_URL_FIELD,
                SHOTGUN_JIRA_ID_FIELD,
                "content",
                "sg_description",
            ],
        )
        jira_issue = bridge.jira.issue(jira_issue.key)

        self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 1)
        self.assertEqual(len(bridge._jira.worklogs(jira_issue.key)), 1)

        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])

    def test_fptr_to_jira_sync_existing_entity_parent_not_synced(self, mocked_sg):
        """
        Check that is a parent entity not synced is linked to a sync entity, it won't be synced in Jira.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is configured to work both way
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the parent entity shouldn't be created in Jira
        """

        sg_mocked_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_mocked_event["meta"]["attribute_name"] = "entity"

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_asset = copy.deepcopy(mock_shotgun.SG_ASSET)
        mocked_sg_asset["tasks"] = [mocked_sg_task]
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_asset)

        self.assertRaises(AttributeError, jira_issue.get_field, "parent")

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Task",
                mock_shotgun.SG_TASK["id"],
                sg_mocked_event,
            )
        )

        sg_asset = bridge.shotgun.find_one(
            "Asset",
            [["id", "is", mock_shotgun.SG_ASSET["id"]]],
            [SHOTGUN_JIRA_ID_FIELD],
        )

        self.assertEqual(sg_asset[SHOTGUN_JIRA_ID_FIELD], None)
        self.assertEqual(jira_issue.get_field("parent"), None)

    def test_fptr_to_jira_sync_existing_entity_parent_synced(self, mocked_sg):
        """
        Check that is a synced parent entity is linked to a sync entity, they will be linked in Jira (event from parent to child).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is configured to work both way
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the parent issue should be linked to the associated child issue in Jira
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        jira_epic = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_ASSET)
        mocked_sg_asset = copy.deepcopy(mock_shotgun.SG_ASSET)
        mocked_sg_asset["tasks"] = [mocked_sg_task]
        mocked_sg_asset[SHOTGUN_JIRA_ID_FIELD] = jira_epic.key
        mocked_sg_asset[SHOTGUN_SYNC_IN_JIRA_FIELD] = True
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_asset)

        self.assertRaises(AttributeError, jira_issue.get_field, "parent")

        bridge.sync_in_jira(
            self.HANDLER_NAME,
            "Asset",
            mock_shotgun.SG_ASSET["id"],
            mock_shotgun.SG_ASSET_CHANGE_EVENT,
        )

        self.assertTrue(jira_issue.get_field("parent"), jira_epic.key)

    def test_fptr_to_jira_sync_existing_entity_child_synced(self, mocked_sg):
        """
        Check that is a synced child entity is linked to a sync entity, they will be linked in Jira (event from child to parent).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is configured to work both way
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the child issue should be linked to the associated parent issue in Jira
        """

        sg_mocked_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_mocked_event["meta"]["attribute_name"] = "entity"

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        jira_epic = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_ASSET)
        mocked_sg_asset = copy.deepcopy(mock_shotgun.SG_ASSET)
        mocked_sg_asset[SHOTGUN_JIRA_ID_FIELD] = jira_epic.key
        mocked_sg_asset[SHOTGUN_SYNC_IN_JIRA_FIELD] = True
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_asset)

        bridge.shotgun.update(
            mocked_sg_task["type"], mocked_sg_task["id"], {"entity": mocked_sg_asset}
        )

        self.assertRaises(AttributeError, jira_issue.get_field, "parent")

        bridge.sync_in_jira(
            self.HANDLER_NAME,
            "Task",
            mock_shotgun.SG_TASK["id"],
            sg_mocked_event,
        )

        self.assertTrue(jira_issue.get_field("parent"), jira_epic.key)

    def test_fptr_to_jira_sync_existing_entity_fields_directions(self, mocked_sg):
        """
        Check that the sync directions for fields are working correctly.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is configured to work both way
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the fields should be updated according to the sync direction defined for each of them in the settings
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        sg_mocked_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_mocked_event["meta"]["attribute_name"] = SHOTGUN_SYNC_IN_JIRA_FIELD

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertNotEqual(jira_issue.fields.summary, mocked_sg.SG_TASK["content"])
        self.assertNotEqual(
            jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"]
        )
        self.assertNotEqual(
            jira_issue.fields.description, mocked_sg.SG_TASK["due_date"]
        )

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Task",
                mock_shotgun.SG_TASK["id"],
                sg_mocked_event,
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", mock_shotgun.SG_TASK["id"]]],
            [
                SHOTGUN_JIRA_URL_FIELD,
                SHOTGUN_JIRA_ID_FIELD,
                "content",
                "sg_description",
            ],
        )
        jira_issue = bridge.jira.issue(jira_issue.key)

        # direction for this field is empty aka "both_way"
        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        # direction for this field is "sg_to_jira"
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])
        # direction for this field is "jira_to_sg"
        self.assertNotEqual(jira_issue.fields.duedate, mocked_sg.SG_TASK["due_date"])

    def test_fptr_to_jira_sync_status(self, mocked_sg):
        """
        Check that the status syncing is working correctly.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is not set, meaning that it would be both_way by default
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira Issue status should be correctly updated
        """

        jira_status = "To Do"

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        sg_mocked_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_mocked_event["meta"]["attribute_name"] = "sg_status_list"

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertNotEqual(jira_issue.fields.status.name, jira_status)

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Task",
                mock_shotgun.SG_TASK["id"],
                sg_mocked_event,
            )
        )

        self.assertEqual(jira_issue.fields.status.name, jira_status)

    def test_fptr_to_jira_sync_status_both_way(self, mocked_sg):
        """
        Check that the status syncing direction is working correctly.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is configured to work both way
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira Issue status should be correctly updated
        """

        jira_status = "To Do"

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_status_both_way"
        )

        sg_mocked_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_mocked_event["meta"]["attribute_name"] = "sg_status_list"

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertNotEqual(jira_issue.fields.status.name, jira_status)

        self.assertTrue(
            bridge.sync_in_jira(
                "entities_generic_status_both_way",
                "Task",
                mock_shotgun.SG_TASK["id"],
                sg_mocked_event,
            )
        )

        self.assertEqual(jira_issue.fields.status.name, jira_status)

    def test_fptr_to_jira_sync_status_sg_to_jira(self, mocked_sg):
        """
        Check that the status syncing direction is working correctly when specified from FPTR to Jira.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is configured to work from FPTR to Jira
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira Issue status should be correctly updated
        """

        jira_status = "To Do"

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_status_sg_to_jira"
        )

        sg_mocked_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_mocked_event["meta"]["attribute_name"] = "sg_status_list"

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertNotEqual(jira_issue.fields.status.name, jira_status)

        self.assertTrue(
            bridge.sync_in_jira(
                "entities_generic_status_sg_to_jira",
                "Task",
                mock_shotgun.SG_TASK["id"],
                sg_mocked_event,
            )
        )

        self.assertEqual(jira_issue.fields.status.name, jira_status)

    def test_fptr_to_jira_sync_status_jira_to_sg(self, mocked_sg):
        """
        Check that the status syncing direction is working correctly when specified from Jira to FPTR.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is configured to work from Jira to FPTR
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira Issue status should not be updated
        """

        jira_status = "To Do"

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_status_jira_to_sg"
        )

        sg_mocked_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_mocked_event["meta"]["attribute_name"] = "sg_status_list"

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertNotEqual(jira_issue.fields.status.name, jira_status)

        self.assertTrue(
            bridge.sync_in_jira(
                "entities_generic_status_jira_to_sg",
                "Task",
                mock_shotgun.SG_TASK["id"],
                sg_mocked_event,
            )
        )

        self.assertNotEqual(jira_issue.fields.status.name, jira_status)

    # -------------------------------------------------------------------------------
    # FPTR to Jira Sync - Entity Delete Event
    # -------------------------------------------------------------------------------
    def test_fptr_to_jira_entity_deletion_not_supported(self, mocked_sg):
        """
        If a FPTR entity other than a Note/TimeLog has been deleted in FPTR,
        the event will be rejected as deletion is not supported by the Bridge.
        """

        mocked_sg_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        mocked_sg_event["meta"]["attribute_name"] = "retirement_date"

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                mocked_sg.SG_TASK,
                mock_shotgun.SG_TASK["id"],
                mocked_sg_event,
            )
        )

    # -------------------------------------------------------------------------------
    # FPTR to Jira Sync - TimeLog Change Event (Timelog creation/update)
    # -------------------------------------------------------------------------------

    def test_fptr_to_jira_sync_new_timelog_not_linked_to_a_synced_entity(
        self, mocked_sg
    ):
        """
        Check that no Jira Issue worklog won't be created in Jira.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is NOT flagged as ready to sync in FPTR
        - the sync direction is not set, meaning that it will be both_way by default
        Expected result:
        - the event should be rejected
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, sync_in_jira=False)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["entity"] = sg_mocked_task
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "TimeLog",
                mock_shotgun.SG_TIMELOG["id"],
                mock_shotgun.SG_TIMELOG_CHANGE_EVENT,
            )
        )

    def test_fptr_to_jira_sync_new_timelog_linked_to_a_synced_entity(self, mocked_sg):
        """
        Check that the Jira Issue worklog associated to the FPTR TimeLog is correctly created in Jira.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is not set, meaning that it will be both_way by default
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira worklog should be created
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["entity"] = mocked_sg_task
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        self.assertEqual(bridge._jira.worklogs(jira_issue.key), [])

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "TimeLog",
                mock_shotgun.SG_TIMELOG["id"],
                mock_shotgun.SG_TIMELOG_CHANGE_EVENT,
            )
        )

        jira_worklogs = bridge._jira.worklogs(jira_issue.key)
        self.assertEqual(len(jira_worklogs), 1)
        worklog_key = "%s/%s" % (jira_issue.key, jira_worklogs[0].id)

        sg_timelog = bridge.shotgun.find_one(
            "TimeLog", [["id", "is", mocked_sg_timelog["id"]]], [SHOTGUN_JIRA_ID_FIELD]
        )

        self.assertEqual(sg_timelog[SHOTGUN_JIRA_ID_FIELD], worklog_key)

    def test_fptr_to_jira_sync_existing_timelog(self, mocked_sg):
        """
        Check that the Jira Issue worklog associated to the FPTR TimeLog is correctly updated in Jira.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is not set, meaning that it will be both_way by default
        - the Worklog already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira worklog should be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(jira_issue, timeSpentSeconds=0)

        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["entity"] = mocked_sg_task
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_worklog.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "TimeLog",
                mock_shotgun.SG_TIMELOG["id"],
                mock_shotgun.SG_TIMELOG_CHANGE_EVENT,
            )
        )

        self.assertEqual(len(bridge._jira.worklogs(jira_issue.key)), 1)
        jira_worklog = bridge._jira.worklog(jira_issue.key, jira_worklog.id)
        self.assertEqual(
            jira_worklog.timeSpentSeconds, mock_shotgun.SG_TIMELOG["duration"] * 60
        )

    # -------------------------------------------------------------------------------
    # FPTR to Jira Sync - TimeLog Delete Event
    # -------------------------------------------------------------------------------

    def test_fptr_to_jira_delete_timelog_deletion_disabled(self, mocked_sg):
        """
        Check that the event will be rejected if the sync deletion direction is not set for the TimeLog entity.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        mocked_sg_event = copy.deepcopy(mock_shotgun.SG_TIMELOG_CHANGE_EVENT)
        mocked_sg_event["meta"]["attribute_name"] = "retirement_date"

        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "TimeLog",
                mock_shotgun.SG_TIMELOG["id"],
                mocked_sg_event,
            )
        )

    def test_fptr_to_jira_delete_timelog_not_linked_to_synced_entity(self, mocked_sg):
        """
        Check that the event will be rejected if the deleted TimeLog is not associated to a synced entity.
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_both_way_deletion"
        )

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, sync_in_jira=False)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["__retired"] = True
        mocked_sg_timelog["entity"] = [sg_mocked_task]
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        mocked_sg_event = copy.deepcopy(mock_shotgun.SG_NOTE_CHANGE_EVENT)
        mocked_sg_event["meta"]["attribute_name"] = "retirement_date"

        self.assertFalse(
            bridge.sync_in_jira(
                "entities_generic_both_way_deletion",
                "TimeLog",
                mock_shotgun.SG_TIMELOG["id"],
                mocked_sg_event,
            )
        )

    def test_fptr_to_jira_delete_timelog_linked_to_synced_entity_both_way_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the Jira Issue worklog associated to the FPTR TimeLog is correctly deleted in Jira (sync direction set both way).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync deletion direction is set to "both_way"
        - the Worklog already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira worklog should be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_both_way_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(jira_issue)
        self.assertEqual(len(bridge._jira.worklogs(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["__retired"] = True
        mocked_sg_timelog["entity"] = [sg_mocked_task]
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_worklog.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        mocked_sg_event = copy.deepcopy(mock_shotgun.SG_TIMELOG_CHANGE_EVENT)
        mocked_sg_event["meta"]["attribute_name"] = "retirement_date"

        self.assertTrue(
            bridge.sync_in_jira(
                "entities_generic_both_way_deletion",
                "TimeLog",
                mock_shotgun.SG_TIMELOG["id"],
                mocked_sg_event,
            )
        )

        self.assertEqual(bridge._jira.worklogs(jira_issue.key), [])

    def test_fptr_to_jira_delete_timelog_linked_to_synced_entity_sg_to_jira_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the Jira Issue worklog associated to the FPTR TimeLog is correctly deleted in Jira (sync direction set from FPTR to Jira).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync deletion direction is set to "sg_to_jira"
        - the Worklog already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira worklog should be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_sg_to_jira_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(jira_issue)
        self.assertEqual(len(bridge._jira.worklogs(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["__retired"] = True
        mocked_sg_timelog["entity"] = [sg_mocked_task]
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_worklog.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        mocked_sg_event = copy.deepcopy(mock_shotgun.SG_TIMELOG_CHANGE_EVENT)
        mocked_sg_event["meta"]["attribute_name"] = "retirement_date"

        self.assertTrue(
            bridge.sync_in_jira(
                "entities_generic_sg_to_jira_deletion",
                "TimeLog",
                mock_shotgun.SG_TIMELOG["id"],
                mocked_sg_event,
            )
        )

        self.assertEqual(bridge._jira.worklogs(jira_issue.key), [])

    def test_fptr_to_jira_delete_timelog_linked_to_synced_entity_jira_to_sg_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the Jira Issue worklog associated to the FPTR TimeLog is not deleted in Jira (sync direction set from Jira to FPTR).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync deletion direction is set to "jira_to_sg"
        - the Worklog already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira comment should not be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_jira_to_sg_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(jira_issue)
        self.assertEqual(len(bridge._jira.worklogs(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["__retired"] = True
        mocked_sg_timelog["entity"] = [sg_mocked_task]
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_worklog.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        mocked_sg_event = copy.deepcopy(mock_shotgun.SG_TIMELOG_CHANGE_EVENT)
        mocked_sg_event["meta"]["attribute_name"] = "retirement_date"

        self.assertFalse(
            bridge.sync_in_jira(
                "entities_generic_jira_to_sg_deletion",
                "TimeLog",
                mock_shotgun.SG_TIMELOG["id"],
                mocked_sg_event,
            )
        )

    # -------------------------------------------------------------------------------
    # FPTR to Jira Sync - Note Change Event (Note creation/update)
    # -------------------------------------------------------------------------------

    def test_fptr_to_jira_sync_new_note_not_linked_to_a_synced_entity(self, mocked_sg):
        """
        Check that no Jira Issue comment won't be created in Jira.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is NOT flagged as ready to sync in FPTR
        - the sync direction is not set, meaning that it will be both_way by default
        Expected result:
        - the event should be rejected
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, sync_in_jira=False)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["tasks"] = [sg_mocked_task]
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Note",
                mock_shotgun.SG_NOTE["id"],
                mock_shotgun.SG_NOTE_CHANGE_EVENT,
            )
        )

    def test_fptr_to_jira_sync_new_note_linked_to_a_synced_entity(self, mocked_sg):
        """
        Check that the Jira Issue comment associated to the FPTR Note is correctly created in Jira.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is not set, meaning that it will be both_way by default
        - the Issue already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira comment should be created
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["tasks"] = [mocked_sg_task]
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        self.assertEqual(bridge._jira.comments(jira_issue.key), [])

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Note",
                mock_shotgun.SG_NOTE["id"],
                mock_shotgun.SG_NOTE_CHANGE_EVENT,
            )
        )

        jira_comments = bridge._jira.comments(jira_issue.key)
        self.assertEqual(len(jira_comments), 1)
        comment_key = "%s/%s" % (jira_issue.key, jira_comments[0].id)

        sg_note = bridge.shotgun.find_one(
            "Note", [["id", "is", mocked_sg_note["id"]]], [SHOTGUN_JIRA_ID_FIELD]
        )

        self.assertEqual(sg_note[SHOTGUN_JIRA_ID_FIELD], comment_key)

    def test_fptr_to_jira_sync_existing_note(self, mocked_sg):
        """
        Check that the Jira Issue comment associated to the FPTR Note is correctly updated in Jira.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync direction is not set, meaning that it will be both_way by default
        - the Comment already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira comment should be updated
        """

        comment_body = "comment created from Jira"

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, comment_body)
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["tasks"] = [mocked_sg_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_comment.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        self.assertTrue(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Note",
                mock_shotgun.SG_NOTE["id"],
                mock_shotgun.SG_NOTE_CHANGE_EVENT,
            )
        )

        self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 1)
        jira_comment = bridge._jira.comment(jira_issue.key, jira_comment.id)
        self.assertNotEqual(jira_comment.body, comment_body)

    # -------------------------------------------------------------------------------
    # FPTR to Jira Sync - Note Deletion Event
    # -------------------------------------------------------------------------------

    def test_fptr_to_jira_delete_note_deletion_disabled(self, mocked_sg):
        """
        Check that the event will be rejected if the sync deletion direction is not set for the Note entity.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        mocked_sg_event = copy.deepcopy(mock_shotgun.SG_NOTE_CHANGE_EVENT)
        mocked_sg_event["meta"]["attribute_name"] = "retirement_date"

        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME,
                "Note",
                mock_shotgun.SG_NOTE["id"],
                mocked_sg_event,
            )
        )

    def test_fptr_to_jira_delete_note_not_linked_to_synced_entity(self, mocked_sg):
        """
        Check that the event will be rejected if the deleted Note is not associated to a synced entity.
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_both_way_deletion"
        )

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, sync_in_jira=False)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["__retired"] = True
        mocked_sg_note["tasks"] = [sg_mocked_task]
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        mocked_sg_event = copy.deepcopy(mock_shotgun.SG_NOTE_CHANGE_EVENT)
        mocked_sg_event["meta"]["attribute_name"] = "retirement_date"

        self.assertFalse(
            bridge.sync_in_jira(
                "entities_generic_both_way_deletion",
                "Note",
                mock_shotgun.SG_NOTE["id"],
                mocked_sg_event,
            )
        )

    def test_fptr_to_jira_delete_note_linked_to_synced_entity_both_way_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the Jira Issue comment associated to the FPTR Note is correctly deleted in Jira.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync deletion direction is set to "both_way"
        - the Comment already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira comment should be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_both_way_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "my comment")
        self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["__retired"] = True
        mocked_sg_note["tasks"] = [sg_mocked_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_comment.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        mocked_sg_event = copy.deepcopy(mock_shotgun.SG_NOTE_CHANGE_EVENT)
        mocked_sg_event["meta"]["attribute_name"] = "retirement_date"

        self.assertTrue(
            bridge.sync_in_jira(
                "entities_generic_both_way_deletion",
                "Note",
                mock_shotgun.SG_NOTE["id"],
                mocked_sg_event,
            )
        )

        self.assertEqual(bridge._jira.comments(jira_issue.key), [])

    def test_fptr_to_jira_delete_note_linked_to_synced_entity_sg_to_jira_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the Jira Issue comment associated to the FPTR Note is correctly deleted in Jira (sync direction set from FPTR to Jira).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync deletion direction is set to "both_way"
        - the Comment already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira comment should be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_sg_to_jira_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "my comment")
        self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["__retired"] = True
        mocked_sg_note["tasks"] = [sg_mocked_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_comment.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        mocked_sg_event = copy.deepcopy(mock_shotgun.SG_NOTE_CHANGE_EVENT)
        mocked_sg_event["meta"]["attribute_name"] = "retirement_date"

        self.assertTrue(
            bridge.sync_in_jira(
                "entities_generic_sg_to_jira_deletion",
                "Note",
                mock_shotgun.SG_NOTE["id"],
                mocked_sg_event,
            )
        )

        self.assertEqual(bridge._jira.comments(jira_issue.key), [])

    def test_fptr_to_jira_delete_note_linked_to_synced_entity_jira_to_sg_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the Jira Issue comment associated to the FPTR Note is not deleted in Jira (sync direction set from Jira to FPTR).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in FPTR
        - the sync deletion direction is set to "both_way"
        - the Comment already exists in Jira and is correctly associated to the FPTR entity
        Expected result:
        - the Jira comment should not be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_jira_to_sg_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "my comment")
        self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["__retired"] = True
        mocked_sg_note["tasks"] = [sg_mocked_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_comment.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        mocked_sg_event = copy.deepcopy(mock_shotgun.SG_NOTE_CHANGE_EVENT)
        mocked_sg_event["meta"]["attribute_name"] = "retirement_date"

        self.assertFalse(
            bridge.sync_in_jira(
                "entities_generic_jira_to_sg_deletion",
                "Note",
                mock_shotgun.SG_NOTE["id"],
                mocked_sg_event,
            )
        )


# Mock Flow Production Tracking with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
class TestEntitiesGenericHandlerJiraToFPTR(TestEntitiesGenericHandler):
    """Test the sync from Jira to FPTR, covering for the different type of entities."""

    # -------------------------------------------------------------------------------
    # Jira to FPTR Sync - Global checks
    # -------------------------------------------------------------------------------

    def test_jira_to_fptr_bad_webhook_event(self, mocked_sg):
        """The event will be rejected if the webhook event is not supported."""

        bad_webhook_event = copy.deepcopy(mock_jira.ISSUE_CREATED_PAYLOAD)
        bad_webhook_event["webhookEvent"] = "bad_event"

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", "FAKED-01", bad_webhook_event
            )
        )

    def test_jira_to_fptr_missing_jira_entity(self, mocked_sg):
        """The event will be rejected if the jira entity is missing."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", "FAKED-01", mock_jira.ISSUE_CREATED_PAYLOAD
            )
        )

    def test_jira_to_fptr_missing_changelog(self, mocked_sg):
        """The event will be rejected if the changelog is missing."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge)
        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD
        )

        del mocked_jira_event["changelog"]

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", "FAKED-01", mocked_jira_event
            )
        )

    def test_jira_to_fptr_issue_type_not_supported(self, mocked_sg):
        """Reject the event if the issue type is not supported."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        jira_issue = bridge.jira.create_issue(
            fields={"issuetype": bridge.jira.issue_type_by_name("BadIssueType")}
        )
        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD
        )

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

    def test_jira_to_fptr_bad_sync_direction(self, mocked_sg):
        """Reject the event if the sync direction is configured to work from FPTR to Jira."""

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_sg_to_jira")

        jira_issue = self._mock_jira_data(bridge)
        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD
        )

        self.assertFalse(
            bridge.sync_in_shotgun(
                "entities_generic_sg_to_jira",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

    def test_jira_to_fptr_jira_project_not_linked_to_sg_project(self, mocked_sg):
        """Reject the event if the sync direction is configured to work from FPTR to Jira."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge)
        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD
        )

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

    def test_jira_to_fptr_entity_not_flagged_as_sync(self, mocked_sg):
        """Reject the event if the Jira entity is not flagged as synced."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sync_in_fptr="False")
        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD
        )

        self._mock_sg_data(bridge.shotgun)

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

    # -------------------------------------------------------------------------------
    # Jira to FPTR Sync - Issue Created Event
    # -------------------------------------------------------------------------------

    def test_jira_to_fptr_sync_new_entity(self, mocked_sg):
        """
        When a new Jira Issue is synced to FPTR, the associated FPTR entity will be created.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is not set, meaning that it would be both_way by default
        - the entity doesn't exist in FPTR yet
        Expected result:
        - the entity will be created in FPTR
        - the FPTR field "Sync in Jira" will be set to True
        - the Jira fields regarding FPTR data will be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge)
        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD
        )

        self._mock_sg_data(bridge.shotgun)

        sg_task = bridge.shotgun.find_one(
            "Task", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]]
        )

        self.assertEqual(sg_task, None)

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            [SHOTGUN_JIRA_ID_FIELD, SHOTGUN_JIRA_URL_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD],
        )
        self.assertNotEqual(sg_task, None)
        expected_url = {"name": "View in Jira", "url": jira_issue.permalink()}
        self.assertEqual(sg_task[SHOTGUN_JIRA_URL_FIELD], expected_url)
        self.assertEqual(sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD], True)

        self._check_jira_issue(bridge, sg_task, sync_in_fptr="True")

    def test_jira_to_fptr_sync_new_entity_both_way(self, mocked_sg):
        """
        When a new Jira Issue is synced to FPTR, the associated FPTR entity will be created.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is set to both_way
        - the entity doesn't exist in FPTR yet
        Expected result:
        - the entity will be created in FPTR
        - the FPTR field "Sync in Jira" will be set to True
        - the Jira fields regarding FPTR data will be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_both_way")

        jira_issue = self._mock_jira_data(bridge)
        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD
        )

        self._mock_sg_data(bridge.shotgun)

        sg_task = bridge.shotgun.find_one(
            "Task", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]]
        )

        self.assertEqual(sg_task, None)

        self.assertTrue(
            bridge.sync_in_shotgun(
                "entities_generic_both_way", "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            [SHOTGUN_JIRA_ID_FIELD, SHOTGUN_JIRA_URL_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD],
        )
        self.assertNotEqual(sg_task, None)
        expected_url = {"name": "View in Jira", "url": jira_issue.permalink()}
        self.assertEqual(sg_task[SHOTGUN_JIRA_URL_FIELD], expected_url)
        self.assertEqual(sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD], True)

        self._check_jira_issue(bridge, sg_task, sync_in_fptr="True")

    def test_jira_to_fptr_sync_new_entity_jira_to_sg(self, mocked_sg):
        """
        When a new Jira Issue is synced to FPTR, the associated FPTR entity will be created.
        If the sync direction is set to "jira_to_sg", the FPTR field "Sync in Jira" will be set to False.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is set to "jira_to_sg"
        - the entity doesn't exist in FPTR yet
        Expected result:
        - the entity will be created in FPTR
        - the FPTR field "Sync in Jira" will be set to False
        - the Jira fields regarding FPTR data will be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_jira_to_sg")

        jira_issue = self._mock_jira_data(bridge)
        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD
        )

        self._mock_sg_data(bridge.shotgun)

        sg_task = bridge.shotgun.find_one(
            "Task", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]]
        )

        self.assertEqual(sg_task, None)

        self.assertTrue(
            bridge.sync_in_shotgun(
                "entities_generic_jira_to_sg",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            [SHOTGUN_JIRA_ID_FIELD, SHOTGUN_JIRA_URL_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD],
        )
        self.assertNotEqual(sg_task, None)
        expected_url = {"name": "View in Jira", "url": jira_issue.permalink()}
        self.assertEqual(sg_task[SHOTGUN_JIRA_URL_FIELD], expected_url)
        self.assertEqual(sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD], False)

        self._check_jira_issue(bridge, sg_task, sync_in_fptr="True")

    # -------------------------------------------------------------------------------
    # Jira to FPTR Sync - Issue Updated Event
    # -------------------------------------------------------------------------------

    def test_jira_to_fptr_sync_existing_entity_one_field_only(self, mocked_sg):
        """
        When a field of an issue already synced to FPTR is updated in Jira, the associated FPTR entity will be updated
        accordingly.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in Jira
        - the sync direction is configured to work both way
        - the Entity already exists in FPTR and is correctly associated to the Jira issue
        Expected result:
        - only the associated field will be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD
        )

        self.assertNotEqual(jira_issue.fields.summary, mocked_sg.SG_TASK["content"])
        self.assertNotEqual(
            jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"]
        )

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            ["content", "sg_description"],
        )

        self.assertNotEqual(jira_issue.fields.summary, sg_task["content"])
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])

    def test_jira_to_fptr_sync_existing_entity_all_fields(self, mocked_sg):
        """
        When the "Sync to FPTR" field is checked in Jira, a full sync of the entity is done to FPTR.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is configured to work both way
        - the entity already exists in FPTR and is correctly associated to the FPTR entity
        Expected result:
        - all the fields will be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        bridge.jira.add_comment(
            jira_issue, body="jira comment body", author=mock_jira.JIRA_USER
        )
        bridge.jira.add_worklog(
            jira_issue,
            timeSpentSeconds=0,
            comment="jira worklog body",
            author=mock_jira.JIRA_USER,
        )

        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD
        )
        mocked_jira_event["changelog"]["items"][0]["field"] = "Sync In FPTR"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "customfield_11504"

        sg_notes = bridge.shotgun.find("Note", [["tasks", "is", mocked_sg_task]])
        self.assertEqual(len(sg_notes), 0)

        sg_timelogs = bridge.shotgun.find("TimeLog", [["entity", "is", mocked_sg_task]])
        self.assertEqual(len(sg_timelogs), 0)

        self.assertNotEqual(jira_issue.fields.summary, mocked_sg.SG_TASK["content"])
        self.assertNotEqual(
            jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"]
        )

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            ["content", "sg_description"],
        )

        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])

        sg_notes = bridge.shotgun.find("Note", [["tasks", "is", mocked_sg_task]])
        self.assertEqual(len(sg_notes), 1)

        sg_timelogs = bridge.shotgun.find("TimeLog", [["entity", "is", mocked_sg_task]])
        self.assertEqual(len(sg_timelogs), 1)

    def test_jira_automation_full_sync(self, mocked_sg):
        """
        A Jira Project Automation full sync.
        """
        _, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        bridge.jira.add_comment(
            jira_issue, body="My comment in jira", author=mock_jira.JIRA_USER
        )
        bridge.jira.add_worklog(
            jira_issue,
            timeSpentSeconds=240,
            comment="My comment in timelog",
            author=mock_jira.JIRA_USER,
        )

        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        payload = {
            "source": "jira_project_automation",
            "user": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
            JIRA_EVENT_AUTOMATION_FULL_SYNC: True,
        }

        normalized_event = normalize_automation_request(
            bridge, "Issue", jira_issue.key, payload
        )

        # The normalizer builds a full-sync, changelog-less event.
        self.assertTrue(normalized_event.get(JIRA_EVENT_AUTOMATION_FULL_SYNC))
        self.assertNotIn("changelog", normalized_event)

        # The handler re-fetches the issue by event["issue"]["id"]. Real Jira
        # resolves issues by their numeric id, but the mock only looks them up
        # by key, so mirror _mock_jira_event and use the key here.
        normalized_event["issue"]["id"] = jira_issue.key

        sg_notes = bridge.shotgun.find("Note", [["tasks", "is", mocked_sg_task]])
        self.assertEqual(len(sg_notes), 0)

        sg_timelogs = bridge.shotgun.find("TimeLog", [["entity", "is", mocked_sg_task]])
        self.assertEqual(len(sg_timelogs), 0)

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, normalized_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            ["content", "sg_description"],
        )

        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])

        sg_note = bridge.shotgun.find_one(
            "Note", [["tasks", "is", mocked_sg_task]], ["content"]
        )
        self.assertEqual(sg_note["content"], "My comment in jira")

        # duration is stored in minutes: 240s / 60 == 4.
        sg_timelog = bridge.shotgun.find_one(
            "TimeLog", [["entity", "is", mocked_sg_task]], ["duration"]
        )
        self.assertEqual(sg_timelog["duration"], 4)

    def test_full_sync_continues_when_comment_maps_to_duplicate_notes(self, mocked_sg):
        """
        During a full sync, a Jira comment that resolves to more than one FPTR
        Note (duplicate entities sharing the same Jira key) is ambiguous and
        can't be synced, but this must not abort the whole sync. The sync
        completes without raising and reports the error (returns False).

        Covered for both full-sync entry points: a "Sync In FPTR" changelog and
        a Jira Project Automation payload normalized without a changelog.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(
            jira_issue, body="jira comment body", author=mock_jira.JIRA_USER
        )

        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        # Two Notes sharing the comment's Jira key make the comment ambiguous.
        # This simulates corrupted FPTR data (a duplicated entity), not normal
        # operation: the comment should normally map to a single Note.
        sg_jira_key = "%s/%s" % (jira_issue.key, jira_comment.id)
        for note_id in (101, 102):
            mocked_note = copy.deepcopy(mock_shotgun.SG_NOTE)
            mocked_note["id"] = note_id
            mocked_note["tasks"] = [mocked_sg_task]
            mocked_note[SHOTGUN_JIRA_ID_FIELD] = sg_jira_key
            self.add_to_sg_mock_db(bridge.shotgun, mocked_note)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD
        )
        mocked_jira_event["changelog"]["items"][0]["field"] = "Sync In FPTR"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "customfield_11504"

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        payload = {
            "source": "jira_project_automation",
            "user": {"accountId": mock_jira.JIRA_USER_2["accountId"]},
        }

        normalized_event = normalize_automation_request(
            bridge, "Issue", jira_issue.key, payload
        )

        # The handler re-fetches the issue by event["issue"]["id"]. Real Jira
        # resolves issues by their numeric id, but the mock only looks them up
        # by key, so mirror _mock_jira_event and use the key here.
        normalized_event["issue"]["id"] = jira_issue.key

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, normalized_event
            )
        )

    def test_sync_jira_fields_to_sg(self, mocked_sg):
        """
        Directly exercise _sync_jira_fields_to_sg.

        - happy path: a full sync writes every mapped Task field onto the FPTR
          Task (the summary/description field mappings and the status mapping)
          and returns True.
        - error branch: when a target FPTR field is not editable, the field is
          skipped, nothing is written, and the method reports the error by
          returning False.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
        handler = syncer.handlers[0]

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        # Happy path: full sync (jira_fields=None) of every mapped Task field.
        self.assertTrue(
            handler._sync_jira_fields_to_sg(jira_issue, jira_issue.key, mocked_sg_task)
        )
        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", mocked_sg_task["id"]]],
            ["content", "sg_description", "sg_status_list"],
        )
        self.assertEqual(sg_task["content"], jira_issue.fields.summary)
        self.assertEqual(sg_task["sg_description"], jira_issue.fields.description)
        self.assertEqual(sg_task["sg_status_list"], "ip")

        # Error branch: a non-editable target FPTR field is skipped and
        # reported. jira_fields is explicit so this stays a fields-only sync.
        with mock.patch.object(
            handler._shotgun,
            "get_field_schema",
            return_value={"editable": {"value": False}},
        ):
            self.assertFalse(
                handler._sync_jira_fields_to_sg(
                    jira_issue, jira_issue.key, mocked_sg_task, jira_fields=["summary"]
                )
            )

    def test_jira_to_fptr_sync_existing_entity_parent_not_synced(self, mocked_sg):
        """
        Check that is a parent entity not synced is linked to a sync entity, it won't be synced in FPTR.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in Jira
        - the sync direction is configured to work both way
        - the Task already exists in FPTR and is correctly associated to the Jira Issue
        Expected result:
        - the parent entity shouldn't be created in FPTR
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        jira_epic = self._mock_jira_data(
            bridge, sg_entity=mock_shotgun.SG_ASSET, sync_in_fptr="False"
        )
        jira_issue.update(fields={"parent": jira_epic})

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD
        )
        mocked_jira_event["changelog"]["items"][0]["field"] = "parent"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "parent"

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_asset = bridge.shotgun.find_one(
            "Asset",
            [["id", "is", mock_shotgun.SG_ASSET["id"]]],
        )

        self.assertEqual(sg_asset, None)

    def test_jira_to_fptr_sync_existing_entity_parent_synced(self, mocked_sg):
        """
        Check that is a synced parent entity is linked to a sync entity, they will be linked in FPTR

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the entity is flagged as ready to sync in Jira
        - the sync direction is configured to work both way
        - the entity already exists in FPTR and is correctly associated to the Jira Issue
        Expected result:
        - the parent entity should be linked to the associated child entity in FPTR
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        jira_epic = self._mock_jira_data(
            bridge, sg_entity=mock_shotgun.SG_ASSET, issue_type_name="Epic"
        )
        mocked_sg_asset = copy.deepcopy(mock_shotgun.SG_ASSET)
        mocked_sg_asset[SHOTGUN_JIRA_ID_FIELD] = jira_epic.key
        mocked_sg_asset[SHOTGUN_SYNC_IN_JIRA_FIELD] = True
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_asset)

        jira_issue.update(fields={"parent": jira_epic})

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD
        )
        mocked_jira_event["changelog"]["items"][0]["field"] = "parent"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "parent"

        sg_task = bridge.shotgun.find_one(
            "Task", [["id", "is", mock_shotgun.SG_TASK["id"]]], ["entity"]
        )
        self.assertEqual(sg_task["entity"], None)

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task", [["id", "is", mock_shotgun.SG_TASK["id"]]], ["entity"]
        )
        self.assertEqual(sg_task["entity"]["id"], mock_shotgun.SG_ASSET["id"])

    def test_jira_to_fptr_sync_existing_entity_fields_directions(self, mocked_sg):
        """
        Check that the sync directions for fields are working correctly.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is configured to work both way
        - the entity already exists in FPTR and is correctly associated to the Jira issue
        Expected result:
        - the fields should be updated according to the sync direction defined for each of them in the settings
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD
        )
        mocked_jira_event["changelog"]["items"][0]["field"] = "Sync In FPTR"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "customfield_11504"

        self.assertNotEqual(jira_issue.fields.summary, mocked_sg.SG_TASK["content"])
        self.assertNotEqual(
            jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"]
        )
        self.assertNotEqual(
            jira_issue.fields.description, mocked_sg.SG_TASK["due_date"]
        )

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", mock_shotgun.SG_TASK["id"]]],
            [
                SHOTGUN_JIRA_URL_FIELD,
                SHOTGUN_JIRA_ID_FIELD,
                "content",
                "sg_description",
            ],
        )
        jira_issue = bridge.jira.issue(jira_issue.key)

        # direction for this field is empty aka "both_way"
        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        # direction for this field is "sg_to_jira"
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])
        # direction for this field is "jira_to_sg"
        self.assertNotEqual(jira_issue.fields.duedate, mocked_sg.SG_TASK["due_date"])

    def test_jira_to_fptr_sync_status(self, mocked_sg):
        """
        Check that the status syncing is working correctly.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is not set, meaning that it would be both_way by default
        - the entity already exists in FPTR and is correctly associated to the Jira issue
        Expected result:
        - the FPTR entity status should be correctly updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertNotEqual(sg_mocked_task["sg_status_list"], "ip")

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD
        )
        mocked_jira_event["changelog"]["items"][0]["field"] = "Status"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "status"

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task", [["id", "is", mock_shotgun.SG_TASK["id"]]], ["sg_status_list"]
        )

        self.assertEqual(sg_task["sg_status_list"], "ip")

    def test_fptr_to_jira_sync_status_sg_to_jira(self, mocked_sg):
        """
        Check that the status syncing is working correctly when specified from FPTR to Jira.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is not set, meaning that it would be both_way by default
        - the entity already exists in FPTR and is correctly associated to the Jira issue
        Expected result:
        - the FPTR entity status should not be updated
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_status_sg_to_jira"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertNotEqual(sg_mocked_task["sg_status_list"], "ip")

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD
        )
        mocked_jira_event["changelog"]["items"][0]["field"] = "Status"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "status"

        self.assertTrue(
            bridge.sync_in_shotgun(
                "entities_generic_status_sg_to_jira",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task", [["id", "is", mock_shotgun.SG_TASK["id"]]], ["sg_status_list"]
        )

        self.assertNotEqual(sg_task["sg_status_list"], "ip")

    def test_fptr_to_jira_sync_status_jira_to_sg(self, mocked_sg):
        """
        Check that the status syncing is working correctly when specified from Jira to FPTR.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is not set, meaning that it would be both_way by default
        - the entity already exists in FPTR and is correctly associated to the Jira issue
        Expected result:
        - the FPTR entity status should be correctly updated
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_status_jira_to_sg"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertNotEqual(sg_mocked_task["sg_status_list"], "ip")

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD
        )
        mocked_jira_event["changelog"]["items"][0]["field"] = "Status"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "status"

        self.assertTrue(
            bridge.sync_in_shotgun(
                "entities_generic_status_jira_to_sg",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task", [["id", "is", mock_shotgun.SG_TASK["id"]]], ["sg_status_list"]
        )

        self.assertEqual(sg_task["sg_status_list"], "ip")

    # -------------------------------------------------------------------------------
    # Jira to FPTR Sync - Worklog Created Event
    # -------------------------------------------------------------------------------

    def test_jira_to_fptr_sync_new_worklog_created_by_jira_bridge_user(self, mocked_sg):
        """
        Check that the event will be rejected if the worklog has been created by the Jira Bridge user to avoid infinite loop.

        Expected result:
        - the event should be rejected
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(
            bridge, sg_entity=mock_shotgun.SG_TASK, sync_in_fptr="False"
        )
        jira_worklog = bridge.jira.add_worklog(jira_issue, timeSpentSeconds=0)

        self._mock_sg_data(bridge.shotgun)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.WORKLOG_PAYLOAD, jira_worklog=jira_worklog
        )
        mocked_jira_event["webhookEvent"] = "worklog_created"
        mocked_jira_event["worklog"]["author"]["accountId"] = mock_jira.JIRA_USER[
            "accountId"
        ]

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

    def test_jira_to_fptr_sync_new_worklog_not_linked_to_a_synced_issue(
        self, mocked_sg
    ):
        """
        Check that no FPTR Timelog entity will be created in FPTR.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is NOT flagged as ready to sync in Jira
        - the sync direction is not set, meaning that it will be both_way by default
        Expected result:
        - the event should be rejected
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(
            bridge, sg_entity=mock_shotgun.SG_TASK, sync_in_fptr="False"
        )
        jira_worklog = bridge.jira.add_worklog(jira_issue, timeSpentSeconds=0)

        self._mock_sg_data(bridge.shotgun)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.WORKLOG_PAYLOAD, jira_worklog=jira_worklog
        )
        mocked_jira_event["webhookEvent"] = "worklog_created"

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

    def test_jira_to_fptr_sync_new_worklog_linked_to_a_synced_issue(self, mocked_sg):
        """
        Check that the FPTR TimeLog entity associated to the Jira Worklog is correctly created in FPTR.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is not set, meaning that it will be both_way by default
        Expected result:
        - the FPTR entity TimeLog entity will be created in FPTR
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(
            jira_issue, timeSpentSeconds=0, comment="fake comment"
        )

        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.WORKLOG_PAYLOAD, jira_worklog=jira_worklog
        )
        mocked_jira_event["webhookEvent"] = "worklog_created"

        sg_timelogs = bridge.shotgun.find("TimeLog", [["entity", "is", mocked_sg_task]])
        self.assertEqual(len(sg_timelogs), 0)

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_timelogs = bridge.shotgun.find(
            "TimeLog", [["entity", "is", mocked_sg_task]], [SHOTGUN_JIRA_ID_FIELD]
        )
        self.assertEqual(len(sg_timelogs), 1)
        self.assertEqual(
            sg_timelogs[0][SHOTGUN_JIRA_ID_FIELD],
            "%s/%s" % (jira_issue.key, jira_worklog.id),
        )

    # -------------------------------------------------------------------------------
    # Jira to FPTR Sync - Worklog Updated Event
    # -------------------------------------------------------------------------------

    def test_jira_to_fptr_sync_existing_worklog_updated_by_jira_bridge_user(
        self, mocked_sg
    ):
        """
        Check that the event will be rejected if the worklog has been updated by the Jira Bridge user to avoid infinite loop.

        Expected result:
        - the event should be rejected
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(
            bridge, sg_entity=mock_shotgun.SG_TASK, sync_in_fptr="False"
        )
        jira_worklog = bridge.jira.add_worklog(jira_issue, timeSpentSeconds=0)

        self._mock_sg_data(bridge.shotgun)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.WORKLOG_PAYLOAD, jira_worklog=jira_worklog
        )
        mocked_jira_event["webhookEvent"] = "worklog_updated"
        mocked_jira_event["worklog"]["updateAuthor"]["accountId"] = mock_jira.JIRA_USER[
            "accountId"
        ]

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

    def test_jira_to_fptr_sync_existing_worklog(self, mocked_sg):
        """
        Check that the FPTR TimeLog entity associated to the Jira Worklog is correctly updated in FPTR.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is not set, meaning that it will be both_way by default
        Expected result:
        - the FPTR entity TimeLog entity should be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(
            jira_issue, timeSpentSeconds=0, comment="fake comment"
        )

        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["entity"] = mocked_sg_task
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_worklog.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.WORKLOG_PAYLOAD, jira_worklog=jira_worklog
        )
        mocked_jira_event["webhookEvent"] = "worklog_updated"

        self.assertNotEqual(
            mocked_sg_timelog["duration"], jira_worklog.timeSpentSeconds
        )

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_timelogs = bridge.shotgun.find(
            "TimeLog",
            [
                [
                    SHOTGUN_JIRA_ID_FIELD,
                    "is",
                    "%s/%s" % (jira_issue.key, jira_worklog.id),
                ]
            ],
            ["duration"],
        )

        self.assertEqual(sg_timelogs[0]["duration"], jira_worklog.timeSpentSeconds)

    # -------------------------------------------------------------------------------
    # Jira to FPTR Sync - Worklog Deleted Event
    # -------------------------------------------------------------------------------

    def test_jira_to_fptr_delete_worklog_deletion_disabled(self, mocked_sg):
        """
        Check that the event will be rejected if the sync deletion direction is not set for the Worklog entity.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(
            jira_issue, timeSpentSeconds=0, comment="fake comment"
        )

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.WORKLOG_PAYLOAD, jira_worklog=jira_worklog
        )
        mocked_jira_event["webhookEvent"] = "worklog_deleted"

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

    def test_jira_to_fptr_delete_worklog_not_linked_to_synced_issue(self, mocked_sg):
        """
        Check that the event will be rejected if the deleted Worklog is not associated to a synced Issue.
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_both_way_deletion"
        )

        jira_issue = self._mock_jira_data(
            bridge, sg_entity=mock_shotgun.SG_TASK, sync_in_fptr="False"
        )
        jira_worklog = bridge.jira.add_worklog(
            jira_issue, timeSpentSeconds=0, comment="fake comment"
        )

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.WORKLOG_PAYLOAD, jira_worklog=jira_worklog
        )
        mocked_jira_event["webhookEvent"] = "worklog_deleted"

        self.assertFalse(
            bridge.sync_in_shotgun(
                "entities_generic_both_way_deletion",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

    def test_jira_to_fptr_delete_worklog_linked_to_synced_issue_both_way_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the FPTR TimeLog associated to the Jira Issue Worklog is correctly deleted in FPTR (sync direction set both way).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the issue is flagged as ready to sync in Jira
        - the sync deletion direction is set to "both_way"
        - the TimeLog already exists in FPTR and is correctly associated to the Jira entity
        Expected result:
        - the FPTR timelog should be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_both_way_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(jira_issue)
        self.assertEqual(len(bridge._jira.worklogs(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["entity"] = [sg_mocked_task]
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_worklog.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.WORKLOG_PAYLOAD, jira_worklog=jira_worklog
        )
        mocked_jira_event["webhookEvent"] = "worklog_deleted"

        jira_worklog.delete()

        self.assertTrue(
            bridge.sync_in_shotgun(
                "entities_generic_both_way_deletion",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

        sg_timelogs = bridge.shotgun.find(
            "TimeLog",
            [
                [
                    SHOTGUN_JIRA_ID_FIELD,
                    "is",
                    "%s/%s" % (jira_issue.key, jira_worklog.id),
                ]
            ],
        )

        self.assertEqual(len(sg_timelogs), 0)

    def test_jira_to_fptr_delete_worklog_linked_to_synced_issue_sg_to_jira_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the FPTR TimeLog associated to the Jira Issue Worklog is not deleted in FPTR (sync direction set from FPTR to Jira).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the issue is flagged as ready to sync in Jira
        - the sync deletion direction is set to "sg_to_jira"
        - the TimeLog already exists in FPTR and is correctly associated to the Jira entity
        Expected result:
        - the FPTR timelog should not be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_sg_to_jira_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(jira_issue)
        self.assertEqual(len(bridge._jira.worklogs(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["entity"] = [sg_mocked_task]
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_worklog.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.WORKLOG_PAYLOAD, jira_worklog=jira_worklog
        )
        mocked_jira_event["webhookEvent"] = "worklog_deleted"

        jira_worklog.delete()

        self.assertFalse(
            bridge.sync_in_shotgun(
                "entities_generic_sg_to_jira_deletion",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

    def test_jira_to_fptr_delete_worklog_linked_to_synced_issue_jira_to_sg_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the FPTR TimeLog associated to the Jira Issue Worklog is correctly deleted in FPTR (sync direction set from Jira to FPTR).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the issue is flagged as ready to sync in Jira
        - the sync deletion direction is set to "both_way"
        - the TimeLog already exists in FPTR and is correctly associated to the Jira entity
        Expected result:
        - the FPTR timelog should be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_jira_to_sg_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(jira_issue)
        self.assertEqual(len(bridge._jira.worklogs(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["entity"] = [sg_mocked_task]
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_worklog.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_timelog)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.WORKLOG_PAYLOAD, jira_worklog=jira_worklog
        )
        mocked_jira_event["webhookEvent"] = "worklog_deleted"

        jira_worklog.delete()

        self.assertTrue(
            bridge.sync_in_shotgun(
                "entities_generic_jira_to_sg_deletion",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

        sg_timelogs = bridge.shotgun.find(
            "TimeLog",
            [
                [
                    SHOTGUN_JIRA_ID_FIELD,
                    "is",
                    "%s/%s" % (jira_issue.key, jira_worklog.id),
                ]
            ],
        )

        self.assertEqual(len(sg_timelogs), 0)

    # -------------------------------------------------------------------------------
    # Jira to FPTR Sync - Comment Created Event
    # -------------------------------------------------------------------------------

    def test_jira_to_fptr_sync_new_comment_created_by_jira_bridge_user(self, mocked_sg):
        """
        Check that the event will be rejected if the comment has been created by the Jira Bridge user to avoid infinite loop.

        Expected result:
        - the event should be rejected
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, body="comment body")

        self._mock_sg_data(bridge.shotgun)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.COMMENT_PAYLOAD, jira_comment=jira_comment
        )
        mocked_jira_event["webhookEvent"] = "comment_created"
        mocked_jira_event["comment"]["author"]["accountId"] = mock_jira.JIRA_USER[
            "accountId"
        ]

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

    def test_jira_to_fptr_sync_new_comment_not_linked_to_a_synced_issue(
        self, mocked_sg
    ):
        """
        Check that no FPTR Note entity will be created in FPTR.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is NOT flagged as ready to sync in Jira
        - the sync direction is not set, meaning that it will be both_way by default
        Expected result:
        - the event should be rejected
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(
            bridge, sg_entity=mock_shotgun.SG_TASK, sync_in_fptr="False"
        )
        jira_comment = bridge.jira.add_comment(jira_issue, body="comment body")

        self._mock_sg_data(bridge.shotgun)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.COMMENT_PAYLOAD, jira_comment=jira_comment
        )
        mocked_jira_event["webhookEvent"] = "comment_created"

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

    def test_jira_to_fptr_sync_new_comment_linked_to_a_synced_issue(self, mocked_sg):
        """
        Check that the FPTR Note entity associated to the Jira Comment is correctly created in FPTR.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is not set, meaning that it will be both_way by default
        Expected result:
        - the FPTR Note entity will be created in FPTR
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(
            jira_issue, body="comment body", author=mock_jira.JIRA_USER
        )

        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.COMMENT_PAYLOAD, jira_comment=jira_comment
        )
        mocked_jira_event["webhookEvent"] = "comment_created"

        sg_notes = bridge.shotgun.find("Note", [["tasks", "is", mocked_sg_task]])
        self.assertEqual(len(sg_notes), 0)

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_notes = bridge.shotgun.find(
            "Note", [["tasks", "is", mocked_sg_task]], [SHOTGUN_JIRA_ID_FIELD]
        )
        self.assertEqual(len(sg_notes), 1)
        self.assertEqual(
            sg_notes[0][SHOTGUN_JIRA_ID_FIELD],
            "%s/%s" % (jira_issue.key, jira_comment.id),
        )

    # -------------------------------------------------------------------------------
    # Jira to FPTR Sync - Comment Updated Event
    # -------------------------------------------------------------------------------

    def test_jira_to_fptr_sync_existing_comment_updated_by_jira_bridge_user(
        self, mocked_sg
    ):
        """
        Check that the event will be rejected if the comment has been updated by the Jira Bridge user to avoid infinite loop.

        Expected result:
        - the event should be rejected
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, body="comment body")

        self._mock_sg_data(bridge.shotgun)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.COMMENT_PAYLOAD, jira_comment=jira_comment
        )
        mocked_jira_event["webhookEvent"] = "comment_updated"
        mocked_jira_event["comment"]["updateAuthor"]["accountId"] = mock_jira.JIRA_USER[
            "accountId"
        ]

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

    def test_jira_to_fptr_sync_existing_comment(self, mocked_sg):
        """
        Check that the FPTR Note entity associated to the Jira comment is correctly updated in FPTR.

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the Issue is flagged as ready to sync in Jira
        - the sync direction is not set, meaning that it will be both_way by default
        Expected result:
        - the FPTR Note entity should be updated
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(
            jira_issue,
            timeSpentSeconds=0,
            body="body comment updated",
            author=mock_jira.JIRA_USER,
        )

        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["tasks"] = [mocked_sg_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_comment.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.COMMENT_PAYLOAD, jira_comment=jira_comment
        )
        mocked_jira_event["webhookEvent"] = "comment_updated"

        self.assertNotEqual(mocked_sg_note["content"], jira_comment.body)

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

        sg_notes = bridge.shotgun.find(
            "Note",
            [
                [
                    SHOTGUN_JIRA_ID_FIELD,
                    "is",
                    "%s/%s" % (jira_issue.key, jira_comment.id),
                ]
            ],
            ["content"],
        )

        self.assertEqual(sg_notes[0]["content"], jira_comment.body)

    # -------------------------------------------------------------------------------
    # Jira to FPTR Sync - Comment Deleted Event
    # -------------------------------------------------------------------------------

    def test_jira_to_fptr_delete_comment_deletion_disabled(self, mocked_sg):
        """
        Check that the event will be rejected if the sync deletion direction is not set for the Comment entity.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, body="comment body")

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.COMMENT_PAYLOAD, jira_comment=jira_comment
        )
        mocked_jira_event["webhookEvent"] = "comment_deleted"

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME, "Issue", jira_issue.key, mocked_jira_event
            )
        )

    def test_jira_to_fptr_delete_comment_not_linked_to_synced_issue(self, mocked_sg):
        """
        Check that the event will be rejected if the deleted Comment is not associated to a synced Issue.
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_both_way_deletion"
        )

        jira_issue = self._mock_jira_data(
            bridge, sg_entity=mock_shotgun.SG_TASK, sync_in_fptr="False"
        )
        jira_comment = bridge.jira.add_comment(jira_issue, body="comment body")

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.COMMENT_PAYLOAD, jira_comment=jira_comment
        )
        mocked_jira_event["webhookEvent"] = "comment_deleted"

        self.assertFalse(
            bridge.sync_in_shotgun(
                "entities_generic_both_way_deletion",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

    def test_jira_to_fptr_delete_comment_linked_to_synced_issue_both_way_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the FPTR Note associated to the Jira Issue Comment is correctly deleted in FPTR (sync direction set both way).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the issue is flagged as ready to sync in Jira
        - the sync deletion direction is set to "both_way"
        - the Note already exists in FPTR and is correctly associated to the Jira entity
        Expected result:
        - the FPTR note should be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_both_way_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, body="comment body")
        self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["tasks"] = [sg_mocked_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_comment.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.COMMENT_PAYLOAD, jira_comment=jira_comment
        )
        mocked_jira_event["webhookEvent"] = "comment_deleted"

        jira_comment.delete()

        self.assertTrue(
            bridge.sync_in_shotgun(
                "entities_generic_both_way_deletion",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

        sg_notes = bridge.shotgun.find(
            "Note",
            [
                [
                    SHOTGUN_JIRA_ID_FIELD,
                    "is",
                    "%s/%s" % (jira_issue.key, jira_comment.id),
                ]
            ],
        )

        self.assertEqual(len(sg_notes), 0)

    def test_jira_to_fptr_delete_comment_linked_to_synced_issue_sg_to_jira_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the FPTR Note associated to the Jira Issue Comment is not deleted in FPTR (sync direction set from FPTR to Jira).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the issue is flagged as ready to sync in Jira
        - the sync deletion direction is set to "sg_to_jira"
        - the Note already exists in FPTR and is correctly associated to the Jira entity
        Expected result:
        - the FPTR note should not be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_sg_to_jira_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, body="comment body")
        self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["tasks"] = [sg_mocked_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_comment.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.COMMENT_PAYLOAD, jira_comment=jira_comment
        )
        mocked_jira_event["webhookEvent"] = "comment_deleted"

        jira_comment.delete()

        self.assertFalse(
            bridge.sync_in_shotgun(
                "entities_generic_sg_to_jira_deletion",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

    def test_jira_to_fptr_delete_comment_linked_to_synced_issue_jira_to_sg_sync_deletion(
        self, mocked_sg
    ):
        """
        Check that the FPTR TimeLog associated to the Jira Issue Worklog is correctly deleted in FPTR (sync direction set from Jira to FPTR).

        Test environment:
        - the entity/field mapping has been done correctly in the settings
        - the issue is flagged as ready to sync in Jira
        - the sync deletion direction is set to "both_way"
        - the TimeLog already exists in FPTR and is correctly associated to the Jira entity
        Expected result:
        - the FPTR timelog should be deleted
        """

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_jira_to_sg_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, body="comment body")
        self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["tasks"] = [sg_mocked_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_comment.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)

        mocked_jira_event = self._mock_jira_event(
            jira_issue, mock_jira.COMMENT_PAYLOAD, jira_comment=jira_comment
        )
        mocked_jira_event["webhookEvent"] = "comment_deleted"

        jira_comment.delete()

        self.assertTrue(
            bridge.sync_in_shotgun(
                "entities_generic_jira_to_sg_deletion",
                "Issue",
                jira_issue.key,
                mocked_jira_event,
            )
        )

        sg_notes = bridge.shotgun.find(
            "Note",
            [
                [
                    SHOTGUN_JIRA_ID_FIELD,
                    "is",
                    "%s/%s" % (jira_issue.key, jira_comment.id),
                ]
            ],
        )

        self.assertEqual(len(sg_notes), 0)


@mock.patch("shotgun_api3.Shotgun")
class TestEntitiesGenericHandlerHook(TestEntitiesGenericHandler):
    """Test the hook functionality for the Entities Generic Handler."""

    JIRA_DATE = "2025-02-18T16:45:09.783+0100"

    def test_default_hook(self, mocked_sg):
        """Check the default hook functionality."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        hook_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "sg_jira", "hook.py")
        )
        module_path = sys.modules[syncer.hook.__module__].__file__

        self.assertEqual(hook_path, module_path)
        self.assertNotEqual(syncer.hook.format_sg_date(self.JIRA_DATE), "fixture_date")

    def test_custom_hook(self, mocked_sg):
        """Check the custom hook functionality."""

        syncer, bridge = self._get_syncer(
            mocked_sg, name="entities_generic_custom_hook"
        )

        hook_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "fixtures", "hook.py")
        )
        module_path = sys.modules[syncer.hook.__module__].__file__

        self.assertEqual(hook_path, module_path)
        self.assertEqual(syncer.hook.format_sg_date(self.JIRA_DATE), "fixture_date")


class TestEntitiesGenericHandlerEdgeCases(TestEntitiesGenericHandler):
    """
    The tests below cover the guard clauses and
    error paths that the bridge can't produce inputs for, so they call the
    handler directly and assert on the resulting Jira/FPTR state.
    """

    def _get_handler(self, mocked_sg, name=None):
        """Return the (handler, bridge) pair for the given settings name."""
        syncer, bridge = self._get_syncer(mocked_sg, name=name or self.HANDLER_NAME)
        return syncer.handlers[0], bridge

    def _add_field_mapping(self, handler, sg_entity_type, field_mapping):
        """
        Give the handler its own copy of the settings with an extra field mapping.

        The settings are deep-copied first so the fixture module, which is shared
        by every test, is left untouched.
        """
        entity_mapping = copy.deepcopy(handler._EntitiesGenericHandler__entity_mapping)
        for m in entity_mapping:
            if m["sg_entity"] == sg_entity_type:
                m["field_mapping"].append(field_mapping)
        setattr(handler, "_EntitiesGenericHandler__entity_mapping", entity_mapping)

    def _replace_field_mapping(self, handler, sg_entity_type, field_mapping):
        """Give the handler its own copy of the settings with a new field mapping."""
        entity_mapping = copy.deepcopy(handler._EntitiesGenericHandler__entity_mapping)
        for m in entity_mapping:
            if m["sg_entity"] == sg_entity_type:
                m["field_mapping"] = field_mapping
        setattr(handler, "_EntitiesGenericHandler__entity_mapping", entity_mapping)

    def _drop_entity_mapping(self, handler, sg_entity_type):
        """Give the handler its own copy of the settings without an entity type."""
        entity_mapping = [
            copy.deepcopy(m)
            for m in handler._EntitiesGenericHandler__entity_mapping
            if m["sg_entity"] != sg_entity_type
        ]
        setattr(handler, "_EntitiesGenericHandler__entity_mapping", entity_mapping)


@mock.patch("shotgun_api3.Shotgun")
class TestEntitiesGenericHandlerHelpers(TestEntitiesGenericHandlerEdgeCases):
    """Test the handler's settings lookups, key parsing and Jira entity loading."""

    # -------------------------------------------------------------------------------
    # setup()
    # -------------------------------------------------------------------------------

    def test_setup_missing_sync_in_fptr_jira_field(self, mocked_sg):
        """
        The handler can't work without the custom Jira field driving the sync, so
        setup() must fail with a message naming the missing field.
        """

        handler, bridge = self._get_handler(mocked_sg)

        with mock.patch.object(
            bridge.jira, "get_jira_issue_field_id", return_value=None
        ):
            with self.assertRaises(RuntimeError) as raised:
                handler.setup()

        self.assertEqual(
            str(raised.exception),
            "Missing required custom Jira field %s" % JIRA_SYNC_IN_FPTR_FIELD,
        )

    # -------------------------------------------------------------------------------
    # Settings lookups
    # -------------------------------------------------------------------------------

    def test_get_jira_issue_type_settings(self, mocked_sg):
        """The settings of a mapped Jira issue type are returned, unmapped give None."""

        handler, _ = self._get_handler(mocked_sg)
        get_settings = handler._EntitiesGenericHandler__get_jira_issue_type_settings

        self.assertEqual(get_settings("Task")["sg_entity"], "Task")
        self.assertEqual(get_settings("Epic")["sg_entity"], "Asset")
        self.assertIsNone(get_settings("Bug"))

    def test_get_field_mapping_requires_exactly_one_field(self, mocked_sg):
        """__get_field_mapping() rejects being called with neither or both fields."""

        handler, _ = self._get_handler(mocked_sg)
        get_field_mapping = handler._EntitiesGenericHandler__get_field_mapping

        with self.assertRaises(ValueError) as raised:
            get_field_mapping("Task")
        self.assertEqual(
            str(raised.exception), "jira_field or sg_field must be provided"
        )

        with self.assertRaises(ValueError) as raised:
            get_field_mapping("Task", jira_field="summary", sg_field="content")
        self.assertEqual(
            str(raised.exception),
            "Only jira_field or sg_field must be provided, but not both of them",
        )

        # sanity check: the mapping resolves in both directions
        self.assertEqual(
            get_field_mapping("Task", jira_field="summary")["sg_field"], "content"
        )
        self.assertEqual(
            get_field_mapping("Task", sg_field="content")["jira_field"], "summary"
        )

    def test_get_status_mapping_requires_exactly_one_status(self, mocked_sg):
        """__get_status_mapping() rejects being called with neither or both statuses."""

        handler, _ = self._get_handler(mocked_sg)
        get_status_mapping = handler._EntitiesGenericHandler__get_status_mapping

        with self.assertRaises(ValueError) as raised:
            get_status_mapping("Task")
        self.assertEqual(
            str(raised.exception), "sg_status or jira_status must be provided"
        )

        with self.assertRaises(ValueError) as raised:
            get_status_mapping("Task", jira_status="To Do", sg_status="wtg")
        self.assertEqual(
            str(raised.exception),
            "Only sg_status or jira_status must be provided, but not both of them",
        )

        # sanity check: the mapping resolves in both directions
        self.assertEqual(get_status_mapping("Task", sg_status="wtg"), "To Do")
        self.assertEqual(get_status_mapping("Task", jira_status="To Do"), "wtg")

    # -------------------------------------------------------------------------------
    # Jira key parsing
    # -------------------------------------------------------------------------------

    def test_parse_jira_key_from_sg_entity(self, mocked_sg):
        """
        An entity synced as an Issue has no sub-entity id in its Jira key, while a
        Note/TimeLog key is split into its Issue key and entity id.
        """

        handler, _ = self._get_handler(mocked_sg)
        parse = handler._EntitiesGenericHandler__parse_jira_key_from_sg_entity

        self.assertEqual(
            parse({"type": "Task", "id": 1, SHOTGUN_JIRA_ID_FIELD: "FAKED-001"}),
            ("FAKED-001", None),
        )
        self.assertEqual(
            parse({"type": "Note", "id": 1, SHOTGUN_JIRA_ID_FIELD: "FAKED-001/12"}),
            ("FAKED-001", "12"),
        )

    def test_parse_jira_key_rejects_malformed_key(self, mocked_sg):
        """A Note/TimeLog Jira key must be "<issue key>/<entity id>"."""

        handler, _ = self._get_handler(mocked_sg)
        parse = handler._EntitiesGenericHandler__parse_jira_key_from_sg_entity

        for bad_key in ["FAKED-001", "FAKED-001/", "/12", "FAKED-001/12/34"]:
            with self.assertRaises(ValueError) as raised:
                parse({"type": "Note", "id": 1, SHOTGUN_JIRA_ID_FIELD: bad_key})
            self.assertEqual(
                str(raised.exception),
                f"Invalid Jira key {bad_key}, it must be in the format "
                "'<jira issue key>/<jira entity id>'",
            )

    def test_parse_jira_webhook_event(self, mocked_sg):
        """A webhook event is split into the Jira entity and the action."""

        handler, _ = self._get_handler(mocked_sg)
        parse = handler._EntitiesGenericHandler__parse_jira_webhook_event

        self.assertEqual(parse("comment_created"), ("comment", "created"))
        self.assertEqual(parse("worklog_deleted"), ("worklog", "deleted"))
        # an event without an "<entity>_<action>" shape can't be parsed
        self.assertEqual(parse("nomatch"), (None, None))

    # -------------------------------------------------------------------------------
    # Linked entity helpers
    # -------------------------------------------------------------------------------

    def test_can_sync_to_fptr(self, mocked_sg):
        """Only an Issue whose "Sync In FPTR" field is "True" can be synced."""

        handler, bridge = self._get_handler(mocked_sg)
        can_sync_to_fptr = handler._EntitiesGenericHandler__can_sync_to_fptr

        self.assertTrue(
            can_sync_to_fptr(self._mock_jira_data(bridge, sync_in_fptr="True"))
        )
        self.assertFalse(
            can_sync_to_fptr(self._mock_jira_data(bridge, sync_in_fptr="False"))
        )

        # the field exists but has never been set
        empty_issue = bridge.jira.create_issue(
            fields={
                "issuetype": bridge.jira.issue_type_by_name("Task"),
                bridge.jira.get_jira_issue_field_id(
                    JIRA_SYNC_IN_FPTR_FIELD.lower()
                ): None,
            }
        )
        self.assertFalse(can_sync_to_fptr(empty_issue))

    # -------------------------------------------------------------------------------
    # Jira comment/worklog retrieval
    # -------------------------------------------------------------------------------

    def test_missing_jira_issue_comment(self, mocked_sg):
        """A comment that no longer exists in Jira resolves to None, not an error."""

        handler, bridge = self._get_handler(mocked_sg)

        with mock.patch.object(
            bridge.jira,
            "comment",
            side_effect=jira.JIRAError(text="not found", status_code=404),
        ):
            self.assertIsNone(handler._get_jira_issue_comment("FAKED-001", "1"))

    def test_get_jira_issue_comment_reraises_other_errors(self, mocked_sg):
        """A Jira error other than 404 means something else is wrong: don't hide it."""

        handler, bridge = self._get_handler(mocked_sg)

        with mock.patch.object(
            bridge.jira,
            "comment",
            side_effect=jira.JIRAError(text="boom", status_code=500),
        ):
            with self.assertRaises(jira.JIRAError) as raised:
                handler._get_jira_issue_comment("FAKED-001", "1")

        self.assertEqual(raised.exception.status_code, 500)

    def test_missing_jira_issue_worklog(self, mocked_sg):
        """A worklog that no longer exists in Jira resolves to None, not an error."""

        handler, bridge = self._get_handler(mocked_sg)

        with mock.patch.object(
            bridge.jira,
            "worklog",
            side_effect=jira.JIRAError(text="not found", status_code=404),
        ):
            self.assertIsNone(handler._get_jira_issue_worklog("FAKED-001", "1"))

    def test_get_jira_issue_worklog_reraises_other_errors(self, mocked_sg):
        """A Jira error other than 404 means something else is wrong: don't hide it."""

        handler, bridge = self._get_handler(mocked_sg)

        with mock.patch.object(
            bridge.jira,
            "worklog",
            side_effect=jira.JIRAError(text="boom", status_code=500),
        ):
            with self.assertRaises(jira.JIRAError) as raised:
                handler._get_jira_issue_worklog("FAKED-001", "1")

        self.assertEqual(raised.exception.status_code, 500)

    def test_get_jira_entity_for_issue_linked_to_another_entity(self, mocked_sg):
        """
        A Jira Issue that records a different FPTR entity than the one being synced
        must not be used, otherwise the two entities would overwrite each other.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        # the Issue is loaded as long as it points back at the same entity
        self.assertEqual(
            handler._get_jira_entity(
                {
                    "type": "Task",
                    "id": sg_task["id"],
                    SHOTGUN_JIRA_ID_FIELD: jira_issue.key,
                }
            ),
            jira_issue,
        )

        # ...but not once it claims to be linked to another FPTR Task
        jira_issue.update(fields={bridge.jira.jira_shotgun_id_field: "42"})
        self.assertIsNone(
            handler._get_jira_entity(
                {
                    "type": "Task",
                    "id": sg_task["id"],
                    SHOTGUN_JIRA_ID_FIELD: jira_issue.key,
                }
            )
        )


@mock.patch("shotgun_api3.Shotgun")
class TestEntitiesGenericHandlerFPTRToJiraEdgeCases(
    TestEntitiesGenericHandlerEdgeCases
):
    """Test the guard clauses and error paths of the FPTR to Jira sync."""

    # -------------------------------------------------------------------------------
    # accept_shotgun_event()
    # -------------------------------------------------------------------------------

    def test_accept_sg_event_rejects_jira_to_sg_only_entity(self, mocked_sg):
        """
        An entity configured to only sync from Jira to FPTR must not push anything
        back to Jira.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_jira_to_sg")
        self._mock_sg_data(bridge.shotgun)

        self.assertFalse(
            bridge.sync_in_jira(
                "entities_generic_jira_to_sg",
                "Task",
                mock_shotgun.SG_TASK["id"],
                mock_shotgun.SG_TASK_CHANGE_EVENT,
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task", [["id", "is", mock_shotgun.SG_TASK["id"]]], [SHOTGUN_JIRA_ID_FIELD]
        )
        self.assertIsNone(sg_task[SHOTGUN_JIRA_ID_FIELD])

    def test_accept_sg_event_rejects_deletion_of_entity_synced_as_issue(
        self, mocked_sg
    ):
        """
        Deletion is only supported for the entities that are not flagged as synced
        (Notes and TimeLogs): deleting a Task must not delete its Jira Issue.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        sg_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_event["meta"]["attribute_name"] = "retirement_date"

        self.assertFalse(
            bridge.sync_in_jira(
                self.HANDLER_NAME, "Task", mock_shotgun.SG_TASK["id"], sg_event
            )
        )

        # the Jira Issue is still there
        self.assertEqual(bridge.jira.issue(jira_issue.key), jira_issue)

    def test_accept_sg_event_rejects_already_handled_creation_event(self, mocked_sg):
        """
        Creating an entity in FPTR emits one event per field. The first one creates
        the Jira Issue with every value, so the remaining "in_create" events are
        redundant and must not create a second Issue.
        """

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        sg_event = copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
        sg_event["meta"]["in_create"] = True

        self.assertFalse(
            bridge.sync_in_jira(self.HANDLER_NAME, "Task", sg_task["id"], sg_event)
        )

    def test_accept_sg_event_for_entity_unlinked_from_a_synced_entity(self, mocked_sg):
        """
        A TimeLog/Note unlinked from its synced entity is still accepted, so the
        matching Jira worklog/comment can be cleaned up. If the entity it was
        unlinked from was never synced there is nothing to do.
        """

        handler, bridge = self._get_handler(mocked_sg)
        accept = (
            handler._EntitiesGenericHandler__accept_shotgun_event_for_entities_not_flagged_as_synced
        )

        self._mock_sg_data(bridge.shotgun, sync_in_jira=False)
        sg_timelog = {"type": "TimeLog", "id": 1, "entity": None}
        previous_task = {"type": "Task", "id": 1}

        # single entity fields report the change as "old_value"
        self.assertFalse(accept(sg_timelog, "entity", {"old_value": previous_task}))

        bridge.shotgun.update("Task", 1, {SHOTGUN_SYNC_IN_JIRA_FIELD: True})
        self.assertTrue(accept(sg_timelog, "entity", {"old_value": previous_task}))

        # multi entity fields report it as "removed"
        self.assertTrue(accept(sg_timelog, "entity", {"removed": [previous_task]}))

    def test_accept_sg_event_for_entity_not_flagged_as_synced(self, mocked_sg):
        """An entity that isn't flagged as ready-to-sync is rejected."""

        handler, bridge = self._get_handler(mocked_sg)
        accept = (
            handler._EntitiesGenericHandler__accept_shotgun_event_for_entities_synced_as_issues
        )

        self.assertFalse(
            accept({"type": "Task", "id": 1, SHOTGUN_SYNC_IN_JIRA_FIELD: False}, "Task")
        )

    def test_accept_sg_event_for_issue_type_not_enabled_in_project(self, mocked_sg):
        """
        An issue type the Jira project doesn't offer is rejected: Jira raises a
        KeyError when the type isn't enabled for the project.
        """

        handler, bridge = self._get_handler(mocked_sg)
        accept = (
            handler._EntitiesGenericHandler__accept_shotgun_event_for_entities_synced_as_issues
        )

        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        sg_entity = {
            "type": "Task",
            "id": 1,
            SHOTGUN_SYNC_IN_JIRA_FIELD: True,
            f"project.Project.{SHOTGUN_JIRA_ID_FIELD}": mock_jira.JIRA_PROJECT_KEY,
        }

        with mock.patch.object(
            bridge.jira, "issue_type_by_name", side_effect=KeyError("Unknown")
        ):
            self.assertFalse(accept(sg_entity, "Unknown Issue Type"))

    def test_accept_sg_event_when_required_jira_fields_are_not_enabled(self, mocked_sg):
        """
        The Jira issue type must expose the "Shotgun Type"/"Shotgun ID" fields,
        otherwise there is nowhere to record which FPTR entity the Issue mirrors.
        """

        handler, bridge = self._get_handler(mocked_sg)
        accept = (
            handler._EntitiesGenericHandler__accept_shotgun_event_for_entities_synced_as_issues
        )

        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        sg_entity = {
            "type": "Task",
            "id": 1,
            SHOTGUN_SYNC_IN_JIRA_FIELD: True,
            f"project.Project.{SHOTGUN_JIRA_ID_FIELD}": mock_jira.JIRA_PROJECT_KEY,
        }

        # the issue type is enabled but exposes none of the required fields
        with mock.patch.object(
            bridge.jira, "get_project_issue_type_fields", return_value={}
        ):
            self.assertFalse(accept(sg_entity, "Task"))

        self.assertTrue(accept(sg_entity, "Task"))

    # -------------------------------------------------------------------------------
    # process_shotgun_event()
    # -------------------------------------------------------------------------------

    def test_process_sg_event_with_unresolvable_jira_issue(self, mocked_sg):
        """
        An entity recording a Jira Issue that can't be loaded is left untouched: we
        must not create a second Issue behind the user's back.
        """

        handler, bridge = self._get_handler(mocked_sg)

        self._mock_sg_data(bridge.shotgun)
        bridge.shotgun.update("Task", 1, {SHOTGUN_JIRA_ID_FIELD: "FAKED-999"})

        self.assertFalse(
            handler.process_shotgun_event(
                "Task", 1, copy.deepcopy(mock_shotgun.SG_TASK_CHANGE_EVENT)
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task", [["id", "is", 1]], [SHOTGUN_JIRA_ID_FIELD]
        )
        self.assertEqual(sg_task[SHOTGUN_JIRA_ID_FIELD], "FAKED-999")

    def test_process_sg_event_relinks_timelog_to_another_entity(self, mocked_sg):
        """
        When a TimeLog is moved to another entity, the worklog on the old Issue is
        deleted and a new one is created against the newly linked Issue.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        stale_worklog = bridge.jira.add_worklog(jira_issue, timeSpentSeconds=60)

        sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        sg_timelog["entity"] = sg_task
        sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, stale_worklog.id)
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog)

        sg_event = copy.deepcopy(mock_shotgun.SG_TIMELOG_CHANGE_EVENT)
        sg_event["meta"]["attribute_name"] = "entity"
        sg_event["meta"]["old_value"] = {"type": "Task", "id": sg_task["id"]}
        sg_event["meta"]["new_value"] = {"type": "Task", "id": sg_task["id"]}

        self.assertTrue(
            handler.process_shotgun_event("TimeLog", sg_timelog["id"], sg_event)
        )

        # exactly one worklog, carrying the TimeLog duration, and FPTR points at it
        self.assertEqual(len(jira_issue._worklogs), 1)
        new_worklog = jira_issue._worklogs[0]
        self.assertEqual(
            new_worklog.timeSpentSeconds, mock_shotgun.SG_TIMELOG["duration"] * 60
        )

        sg_timelog = bridge.shotgun.find_one(
            "TimeLog", [["id", "is", sg_timelog["id"]]], [SHOTGUN_JIRA_ID_FIELD]
        )
        self.assertEqual(
            sg_timelog[SHOTGUN_JIRA_ID_FIELD],
            "%s/%s" % (jira_issue.key, new_worklog.id),
        )

    def test_process_sg_event_relinks_note_to_another_entity(self, mocked_sg):
        """
        Same as above for a Note, whose multi-entity "tasks" field reports its
        changes as "removed"/"added" rather than "old_value"/"new_value".
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        stale_comment = bridge.jira.add_comment(jira_issue, "Stale comment")

        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note["tasks"] = [sg_task]
        sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, stale_comment.id)
        self.add_to_sg_mock_db(bridge.shotgun, sg_note)

        sg_event = copy.deepcopy(mock_shotgun.SG_NOTE_CHANGE_EVENT)
        sg_event["meta"]["attribute_name"] = "tasks"
        sg_event["meta"]["removed"] = [{"type": "Task", "id": sg_task["id"]}]
        sg_event["meta"]["added"] = [{"type": "Task", "id": sg_task["id"]}]

        self.assertTrue(handler.process_shotgun_event("Note", sg_note["id"], sg_event))

        self.assertEqual(len(jira_issue._comments), 1)
        new_comment = jira_issue._comments[0]
        self.assertIn(mock_shotgun.SG_NOTE["content"], new_comment.body)

        sg_note = bridge.shotgun.find_one(
            "Note", [["id", "is", sg_note["id"]]], [SHOTGUN_JIRA_ID_FIELD]
        )
        self.assertEqual(
            sg_note[SHOTGUN_JIRA_ID_FIELD],
            "%s/%s" % (jira_issue.key, new_comment.id),
        )

    # -------------------------------------------------------------------------------
    # Jira entity creation and deletion
    # -------------------------------------------------------------------------------

    def test_create_jira_comment_for_note_linked_to_several_tasks(self, mocked_sg):
        """
        A Note can be linked to several Tasks in FPTR but a Jira comment belongs to
        a single Issue, so only one comment is created.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        second_task = copy.deepcopy(mock_shotgun.SG_TASK)
        second_task["id"] = 2
        second_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True
        self.add_to_sg_mock_db(bridge.shotgun, second_task)

        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note["tasks"] = [sg_task, second_task]

        jira_comment, jira_comment_key = handler._create_jira_comment(sg_note)

        self.assertEqual(len(jira_issue._comments), 1)
        self.assertEqual(jira_comment_key, "%s/%s" % (jira_issue.key, jira_comment.id))
        self.assertIn(mock_shotgun.SG_NOTE["subject"], jira_comment.body)
        self.assertIn(mock_shotgun.SG_NOTE["content"], jira_comment.body)

    def test_create_jira_comment_without_a_jira_issue(self, mocked_sg):
        """No comment is created when the linked Issue can't be loaded from Jira."""

        handler, bridge = self._get_handler(mocked_sg)

        self._mock_sg_data(bridge.shotgun)
        bridge.shotgun.update("Task", 1, {SHOTGUN_JIRA_ID_FIELD: "FAKED-999"})
        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", 1]],
            [SHOTGUN_JIRA_ID_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD, "content"],
        )

        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note["tasks"] = [sg_task]

        self.assertEqual(handler._create_jira_comment(sg_note), (None, None))

    def test_create_jira_worklog_without_a_jira_issue(self, mocked_sg):
        """No worklog is created when the linked Issue can't be loaded from Jira."""

        handler, bridge = self._get_handler(mocked_sg)

        self._mock_sg_data(bridge.shotgun)
        bridge.shotgun.update("Task", 1, {SHOTGUN_JIRA_ID_FIELD: "FAKED-999"})
        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", 1]],
            [SHOTGUN_JIRA_ID_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD, "content"],
        )

        sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        sg_timelog["entity"] = sg_task

        self.assertEqual(handler._create_jira_worklog(sg_timelog), (None, None))

    def test_create_jira_issue_reported_by_a_non_human_user(self, mocked_sg):
        """
        An entity created by a script user has no Jira counterpart, so the Issue is
        reported by the Jira user the bridge runs as.
        """

        handler, bridge = self._get_handler(mocked_sg)

        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        jira_project = handler.get_jira_project(mock_jira.JIRA_PROJECT_KEY)

        sg_task = copy.deepcopy(mock_shotgun.SG_TASK)
        sg_task["name"] = sg_task["content"]
        sg_task["created_by"] = {"type": "ApiUser", "id": 7}

        jira_issue, jira_issue_key = handler._create_jira_issue(sg_task, jira_project)

        self.assertEqual(jira_issue.key, jira_issue_key)
        self.assertEqual(
            jira_issue.fields.reporter.accountId, mock_jira.JIRA_USER["accountId"]
        )

    def test_create_jira_issue_without_a_summary_mapping(self, mocked_sg):
        """With no FPTR field mapped to "summary", the entity name field is used."""

        handler, bridge = self._get_handler(mocked_sg)
        self._replace_field_mapping(
            handler,
            "Task",
            [{"sg_field": "sg_description", "jira_field": "description"}],
        )

        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        jira_project = handler.get_jira_project(mock_jira.JIRA_PROJECT_KEY)
        self._mock_sg_data(bridge.shotgun)

        sg_task = copy.deepcopy(mock_shotgun.SG_TASK)
        sg_task["name"] = sg_task["content"]
        sg_task["created_by"] = mock_shotgun.SG_USER

        jira_issue, _ = handler._create_jira_issue(sg_task, jira_project)

        self.assertEqual(jira_issue.fields.summary, mock_shotgun.SG_TASK["content"])

    def test_delete_jira_entity_without_a_jira_entity(self, mocked_sg):
        """Deleting reports failure when the Jira entity can't be found."""

        handler, _ = self._get_handler(mocked_sg)

        self.assertFalse(
            handler._delete_jira_entity(
                {"type": "Task", "id": 1, SHOTGUN_JIRA_ID_FIELD: "FAKED-999"}
            )
        )

    # -------------------------------------------------------------------------------
    # _sync_sg_fields_to_jira()
    # -------------------------------------------------------------------------------

    def test_sync_sg_fields_to_jira_skips_note_task_field(self, mocked_sg):
        """
        The Note/Issue association is handled while processing the event, so the
        "tasks" field itself has nothing to push to the Jira comment.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        sg_note["tasks"] = [sg_task]
        self.add_to_sg_mock_db(bridge.shotgun, sg_note)

        jira_comment = bridge.jira.add_comment(jira_issue, "Untouched comment")

        self.assertTrue(
            handler._sync_sg_fields_to_jira(sg_note, jira_comment, field_name="tasks")
        )
        self.assertEqual(jira_comment.body, "Untouched comment")

    def test_sync_sg_fields_to_jira_syncs_watchers(self, mocked_sg):
        """
        A FPTR field mapped to "watches" is routed to the watcher sync rather than
        being pushed as a regular field value.
        """

        handler, bridge = self._get_handler(mocked_sg)
        self._add_field_mapping(
            handler, "Task", {"sg_field": "addressings_cc", "jira_field": "watches"}
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(
            bridge.shotgun,
            jira_issue=jira_issue,
            extra_fields={"addressings_cc": [mock_shotgun.SG_USER]},
        )

        # the Jira mock has no watcher endpoints, so assert on the calls made
        with mock.patch.object(
            bridge.jira,
            "find_jira_user",
            return_value=mock.Mock(
                accountId=mock_jira.JIRA_USER["accountId"],
                displayName=mock_jira.JIRA_USER["displayName"],
            ),
        ), mock.patch.object(
            bridge.jira,
            "watchers",
            create=True,
            return_value=mock.Mock(watchers=[]),
        ), mock.patch.object(
            bridge.jira, "add_watcher", create=True
        ) as add_watcher:
            self.assertTrue(
                handler._sync_sg_fields_to_jira(
                    sg_task, jira_issue, field_name="addressings_cc"
                )
            )

        add_watcher.assert_called_once_with(
            jira_issue, mock_jira.JIRA_USER["accountId"]
        )

    def test_sync_sg_watchers_to_jira(self, mocked_sg):
        """
        FPTR users are added to the Jira watch list, Jira watchers that are no
        longer in FPTR are removed and non-user entities are ignored.
        """

        handler, bridge = self._get_handler(mocked_sg)
        sg_task = self._mock_sg_data(bridge.shotgun)
        jira_issue = self._mock_jira_data(bridge, sg_entity=sg_task)

        jira_user = mock.Mock(
            accountId=mock_jira.JIRA_USER["accountId"],
            displayName=mock_jira.JIRA_USER["displayName"],
        )
        stale_watcher = mock.Mock(accountId="stale-account", displayName="Zaphod")

        # the Jira mock has no watcher endpoints, so assert on the calls made
        with mock.patch.object(
            bridge.jira, "find_jira_user", return_value=jira_user
        ), mock.patch.object(
            bridge.jira,
            "watchers",
            create=True,
            return_value=mock.Mock(watchers=[jira_user, stale_watcher]),
        ), mock.patch.object(
            bridge.jira, "add_watcher", create=True
        ) as add_watcher, mock.patch.object(
            bridge.jira, "remove_watcher", create=True
        ) as remove_watcher:
            self.assertTrue(
                handler._sync_sg_watchers_to_jira(
                    [mock_shotgun.SG_USER, {"type": "Group", "id": 3}], jira_issue
                )
            )

        # the FPTR user is added, the watcher that is no longer in FPTR is removed
        # and the Group never reaches Jira
        add_watcher.assert_called_once_with(
            jira_issue, mock_jira.JIRA_USER["accountId"]
        )
        remove_watcher.assert_called_once_with(jira_issue, "Zaphod")

    def test_sync_sg_watchers_to_jira_from_single_entity_field(self, mocked_sg):
        """A single-entity FPTR field is accepted as well as a multi-entity one."""

        handler, bridge = self._get_handler(mocked_sg)
        sg_task = self._mock_sg_data(bridge.shotgun)
        jira_issue = self._mock_jira_data(bridge, sg_entity=sg_task)

        jira_user = mock.Mock(
            accountId=mock_jira.JIRA_USER["accountId"],
            displayName=mock_jira.JIRA_USER["displayName"],
        )

        with mock.patch.object(
            bridge.jira, "find_jira_user", return_value=jira_user
        ), mock.patch.object(
            bridge.jira,
            "watchers",
            create=True,
            return_value=mock.Mock(watchers=[jira_user]),
        ), mock.patch.object(
            bridge.jira, "add_watcher", create=True
        ) as add_watcher, mock.patch.object(
            bridge.jira, "remove_watcher", create=True
        ) as remove_watcher:
            self.assertTrue(
                handler._sync_sg_watchers_to_jira(mock_shotgun.SG_USER, jira_issue)
            )

        add_watcher.assert_called_once_with(
            jira_issue, mock_jira.JIRA_USER["accountId"]
        )
        # the only watcher is still in FPTR, nothing to remove
        remove_watcher.assert_not_called()

    def test_sync_sg_status_to_jira_without_mapping(self, mocked_sg):
        """A FPTR status with no Jira counterpart leaves the Jira status alone."""

        handler, bridge = self._get_handler(mocked_sg)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        original_status = jira_issue.fields.status

        self.assertFalse(
            handler._sync_sg_status_to_jira("unmapped_status", "Task", jira_issue)
        )
        self.assertEqual(jira_issue.fields.status, original_status)

    def test_sync_sg_fields_to_jira_skips_non_editable_jira_field(self, mocked_sg):
        """
        A Jira field the issue type doesn't allow editing is reported as a failed
        sync instead of raising when Jira refuses the update.
        """

        handler, bridge = self._get_handler(mocked_sg)
        # "duedate" is a valid Jira field but is not part of the Issue edit meta
        self._add_field_mapping(
            handler, "Task", {"sg_field": "due_date", "jira_field": "duedate"}
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        original_duedate = getattr(jira_issue.fields, "duedate", None)

        self.assertFalse(
            handler._sync_sg_fields_to_jira(sg_task, jira_issue, field_name="due_date")
        )
        self.assertEqual(getattr(jira_issue.fields, "duedate", None), original_duedate)
        self.assertNotEqual(
            getattr(jira_issue.fields, "duedate", None),
            mock_shotgun.SG_TASK["due_date"],
        )

    def test_sync_sg_fields_to_jira_converts_list_values(self, mocked_sg):
        """A multi-value FPTR field is converted to a Jira array value."""

        handler, bridge = self._get_handler(mocked_sg)
        self._add_field_mapping(
            handler, "Task", {"sg_field": "tags", "jira_field": "labels"}
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(
            bridge.shotgun,
            jira_issue=jira_issue,
            extra_fields={"tags": [{"type": "Tag", "id": 1, "name": "urgent"}]},
        )

        self.assertTrue(
            handler._sync_sg_fields_to_jira(sg_task, jira_issue, field_name="tags")
        )
        self.assertEqual(jira_issue.fields.labels, ["urgent"])

    def test_sync_sg_fields_to_jira_when_value_conversion_raises(self, mocked_sg):
        """
        A hook raising while converting a value is reported as a failed sync and
        leaves the Jira Issue untouched.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        original_summary = jira_issue.fields.summary

        with mock.patch.object(
            handler._hook,
            "get_jira_value_from_sg_value",
            side_effect=RuntimeError("boom"),
        ):
            self.assertFalse(
                handler._sync_sg_fields_to_jira(
                    sg_task, jira_issue, field_name="content"
                )
            )

        self.assertEqual(jira_issue.fields.summary, original_summary)

    def test_sync_sg_fields_to_jira_when_value_has_no_jira_equivalent(self, mocked_sg):
        """
        A FPTR value that can't be translated is reported rather than clearing the
        Jira field with an empty value.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        original_summary = jira_issue.fields.summary

        with mock.patch.object(
            handler._hook, "get_jira_value_from_sg_value", return_value=None
        ):
            self.assertFalse(
                handler._sync_sg_fields_to_jira(
                    sg_task, jira_issue, field_name="content"
                )
            )

        self.assertEqual(jira_issue.fields.summary, original_summary)

    def test_sync_sg_fields_to_jira_reports_linked_entity_errors(self, mocked_sg):
        """
        A full sync fails when one of the entity's TimeLogs can't be synced, even
        though the Issue fields themselves went through.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(
            bridge.shotgun, jira_issue=jira_issue, extra_fields={"entity": None}
        )

        # this TimeLog claims a worklog that doesn't exist on the Issue
        sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        sg_timelog["entity"] = sg_task
        sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/999" % jira_issue.key
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog)

        self.assertFalse(handler._sync_sg_fields_to_jira(sg_task, jira_issue))
        # the Issue fields were still synced
        self.assertEqual(jira_issue.fields.summary, mock_shotgun.SG_TASK["content"])

    # -------------------------------------------------------------------------------
    # Linked entities and hierarchy
    # -------------------------------------------------------------------------------

    def test_sync_sg_linked_entities_for_unsupported_entity_type(self, mocked_sg):
        """Nothing is synced for an entity type that isn't in the settings."""

        handler, bridge = self._get_handler(mocked_sg)
        self._drop_entity_mapping(handler, "TimeLog")

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        sg_timelog["entity"] = sg_task
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog)

        self.assertFalse(
            handler._sync_sg_linked_entities_to_jira(sg_task, "TimeLog", jira_issue)
        )
        self.assertEqual(jira_issue._worklogs, [])

    def test_sync_sg_linked_entities_skips_entities_synced_elsewhere(self, mocked_sg):
        """
        A TimeLog already synced to another Jira Issue is left alone rather than
        being duplicated onto this one.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        sg_timelog["entity"] = sg_task
        sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "OTHER-001/1"
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog)

        self.assertFalse(
            handler._sync_sg_linked_entities_to_jira(sg_task, "TimeLog", jira_issue)
        )

        self.assertEqual(jira_issue._worklogs, [])
        sg_timelog = bridge.shotgun.find_one(
            "TimeLog", [["id", "is", sg_timelog["id"]]], [SHOTGUN_JIRA_ID_FIELD]
        )
        self.assertEqual(sg_timelog[SHOTGUN_JIRA_ID_FIELD], "OTHER-001/1")

    def test_sync_hierarchy_with_unmapped_linked_entity(self, mocked_sg):
        """A parent whose entity type isn't in the settings is skipped."""

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertFalse(
            handler._sync_hierarchy_to_jira(
                {"type": "Shot", "id": 1}, jira_issue, "parent"
            )
        )
        self.assertIsNone(getattr(jira_issue.fields, "parent", None))

    def test_sync_hierarchy_with_linked_entity_not_synced(self, mocked_sg):
        """A parent that has no Jira Issue of its own yet is skipped."""

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun)
        self.add_to_sg_mock_db(bridge.shotgun, mock_shotgun.SG_ASSET)

        self.assertFalse(
            handler._sync_hierarchy_to_jira(
                {"type": "Asset", "id": 1}, jira_issue, "parent"
            )
        )
        self.assertIsNone(getattr(jira_issue.fields, "parent", None))

    def test_sync_hierarchy_with_unloadable_jira_issue(self, mocked_sg):
        """A parent whose Jira Issue can't be loaded is skipped."""

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun)

        sg_asset = copy.deepcopy(mock_shotgun.SG_ASSET)
        sg_asset[SHOTGUN_JIRA_ID_FIELD] = "FAKED-999"
        self.add_to_sg_mock_db(bridge.shotgun, sg_asset)

        with mock.patch.object(bridge.jira, "issue", return_value=None):
            self.assertFalse(
                handler._sync_hierarchy_to_jira(
                    {"type": "Asset", "id": 1}, jira_issue, "parent"
                )
            )

        self.assertIsNone(getattr(jira_issue.fields, "parent", None))


@mock.patch("shotgun_api3.Shotgun")
class TestEntitiesGenericHandlerJiraToFPTREdgeCases(
    TestEntitiesGenericHandlerEdgeCases
):
    """Test the guard clauses and error paths of the Jira to FPTR sync."""

    # -------------------------------------------------------------------------------
    # accept_jira_event()
    # -------------------------------------------------------------------------------

    def test_accept_jira_event_rejects_non_issue_resource(self, mocked_sg):
        """The handler only knows how to sync Issue resources."""

        handler, _ = self._get_handler(mocked_sg)

        self.assertFalse(
            handler.accept_jira_event(
                "Project", "UTest", mock_jira.ISSUE_UPDATED_PAYLOAD
            )
        )

    def test_accept_jira_event_rejects_event_without_its_entity(self, mocked_sg):
        """A comment event that carries no "comment" block can't be processed."""

        handler, _ = self._get_handler(mocked_sg)

        self.assertFalse(
            handler.accept_jira_event(
                "Issue", "FAKED-001", {"webhookEvent": "comment_created"}
            )
        )

    def test_accept_jira_event_rejects_comment_without_an_issue(self, mocked_sg):
        """
        A Jira comment only exists as part of an Issue, so an event that references
        none can't be matched to a FPTR entity.
        """

        handler, _ = self._get_handler(mocked_sg)

        comment_event = copy.deepcopy(mock_jira.COMMENT_PAYLOAD)
        del comment_event["issue"]

        self.assertFalse(handler.accept_jira_event("Issue", "FAKED-001", comment_event))

    def test_accept_jira_event_rejects_issue_without_a_project(self, mocked_sg):
        """
        An Issue with no project can't be matched to a FPTR project.

        ``get_jira_issue()`` raises before this guard is reached in practice (see
        the test below), so the Issue is stubbed here to exercise the guard itself.
        """

        handler, bridge = self._get_handler(mocked_sg)

        project_less_issue = mock.MagicMock()
        project_less_issue.fields.issuetype.name = "Task"
        project_less_issue.fields.project = None

        with mock.patch.object(
            handler, "get_jira_issue", return_value=project_less_issue
        ):
            self.assertFalse(
                handler.accept_jira_event(
                    "Issue", "FAKED-001", mock_jira.ISSUE_UPDATED_PAYLOAD
                )
            )

    def test_get_jira_issue_raises_for_issue_without_a_project(self, mocked_sg):
        """Loading an Issue that isn't bound to a project is an error."""

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_issue.update(fields={"project": None})

        with self.assertRaises(RuntimeError) as raised:
            handler.get_jira_issue(jira_issue.key)

        self.assertEqual(
            str(raised.exception),
            "Jira Issue %s is not bound to any Project." % jira_issue.key,
        )

    def test_accept_jira_event_when_sync_in_fptr_field_is_not_enabled(self, mocked_sg):
        """
        The "Sync In FPTR" field must be on the screen for the project and issue
        type, otherwise the Issue has no way to opt in to syncing.
        """

        handler, bridge = self._get_handler(mocked_sg)

        self._mock_sg_data(bridge.shotgun)

        # the Issue is created without the "Sync In FPTR" field, so reading it
        # raises AttributeError the way an unconfigured Jira screen would
        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        jira_issue = bridge.jira.create_issue(
            fields={"issuetype": bridge.jira.issue_type_by_name("Task")}
        )

        jira_event = self._mock_jira_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)

        self.assertFalse(handler.accept_jira_event("Issue", jira_issue.key, jira_event))

    # -------------------------------------------------------------------------------
    # process_jira_event()
    # -------------------------------------------------------------------------------

    def test_process_jira_event_without_a_fptr_entity(self, mocked_sg):
        """
        Nothing is synced when the FPTR entity can't be resolved: here the Issue
        records a FPTR Task that no longer exists.
        """

        handler, bridge = self._get_handler(mocked_sg)

        self.add_to_sg_mock_db(bridge.shotgun, mock_shotgun.SG_PROJECT)
        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)

        jira_event = self._mock_jira_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)

        self.assertFalse(
            handler.process_jira_event("Issue", jira_issue.key, jira_event)
        )
        self.assertEqual(bridge.shotgun.find("Task", []), [])

    def test_process_jira_event_with_parent_association_change(self, mocked_sg):
        """
        A parenting change is reported by Jira as "IssueParentAssociation", which
        carries no field id of its own and maps to the "parent" field.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        jira_event = self._mock_jira_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)
        jira_event["changelog"]["items"] = [{"field": "IssueParentAssociation"}]

        self.assertTrue(handler.process_jira_event("Issue", jira_issue.key, jira_event))

        # the Issue has no parent, so the FPTR link is cleared rather than guessed
        sg_task = bridge.shotgun.find_one(
            "Task", [["id", "is", sg_task["id"]]], ["entity"]
        )
        self.assertIsNone(sg_task["entity"])

    # -------------------------------------------------------------------------------
    # _sync_jira_issue_to_sg() / _sync_jira_entity_to_sg()
    # -------------------------------------------------------------------------------

    def test_sync_jira_issue_to_sg_without_a_name_mapping(self, mocked_sg):
        """With no FPTR field mapped to the name, the Jira summary is used."""

        handler, bridge = self._get_handler(mocked_sg)
        self._replace_field_mapping(
            handler,
            "Task",
            [{"sg_field": "sg_description", "jira_field": "description"}],
        )

        self.add_to_sg_mock_db(bridge.shotgun, mock_shotgun.SG_PROJECT)

        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        jira_issue = bridge.jira.create_issue(
            fields={
                "issuetype": bridge.jira.issue_type_by_name("Task"),
                "summary": "Issue summary",
                bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_ID_FIELD.lower()): "",
                bridge.jira.get_jira_issue_field_id(
                    JIRA_SHOTGUN_TYPE_FIELD.lower()
                ): "",
            }
        )

        sg_task = handler._sync_jira_issue_to_sg(jira_issue)

        self.assertEqual(sg_task["content"], "Issue summary")
        # Jira is updated with the FPTR entity it now mirrors
        self.assertEqual(
            jira_issue.get_field(bridge.jira.jira_shotgun_id_field), str(sg_task["id"])
        )
        self.assertEqual(
            jira_issue.get_field(bridge.jira.jira_shotgun_type_field), "Task"
        )

    def test_sync_jira_entity_to_sg_with_duplicated_issue_keys(self, mocked_sg):
        """
        Two FPTR entities carrying the same Jira key is ambiguous: we can't tell
        which one the comment belongs to, so nothing is created.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        duplicated_task = copy.deepcopy(mock_shotgun.SG_TASK)
        duplicated_task["id"] = 2
        duplicated_task[SHOTGUN_JIRA_ID_FIELD] = jira_issue.key
        self.add_to_sg_mock_db(bridge.shotgun, duplicated_task)

        self.assertFalse(
            handler._sync_jira_entity_to_sg(jira_issue, "1", "Note", "created")
        )
        self.assertEqual(bridge.shotgun.find("Note", []), [])

    def test_sync_jira_entity_to_sg_without_a_synced_issue(self, mocked_sg):
        """A Jira Issue with no FPTR counterpart has nothing to attach a Note to."""

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun)

        self.assertFalse(
            handler._sync_jira_entity_to_sg(jira_issue, "1", "Note", "created")
        )
        self.assertEqual(bridge.shotgun.find("Note", []), [])

    def test_sync_jira_entity_to_sg_deleting_an_unknown_entity(self, mocked_sg):
        """Deleting an entity FPTR never knew about is reported, not created."""

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        self.assertFalse(
            handler._sync_jira_entity_to_sg(jira_issue, "999", "Note", "deleted")
        )
        self.assertEqual(bridge.shotgun.find("Note", []), [])

    # -------------------------------------------------------------------------------
    # _sync_jira_fields_to_sg()
    # -------------------------------------------------------------------------------

    def test_sync_jira_fields_to_sg_syncs_watchers(self, mocked_sg):
        """
        Jira watchers are translated back to FPTR users; watchers with no FPTR
        account are dropped rather than failing the sync.
        """

        handler, bridge = self._get_handler(mocked_sg)
        self._add_field_mapping(
            handler, "Task", {"sg_field": "addressings_cc", "jira_field": "watches"}
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        known_watcher = mock.Mock(accountId=mock_jira.JIRA_USER["accountId"])
        unknown_watcher = mock.Mock(accountId="not-in-fptr")

        # the Jira mock has no watchers endpoint, so it is stubbed here
        with mock.patch.object(
            bridge.jira,
            "watchers",
            create=True,
            return_value=mock.Mock(watchers=[known_watcher, unknown_watcher]),
        ):
            self.assertTrue(
                handler._sync_jira_fields_to_sg(
                    jira_issue, jira_issue.key, sg_task, ["watches"]
                )
            )

        sg_task = bridge.shotgun.find_one(
            "Task", [["id", "is", sg_task["id"]]], ["addressings_cc"]
        )
        self.assertEqual(len(sg_task["addressings_cc"]), 1)
        self.assertEqual(sg_task["addressings_cc"][0]["id"], mock_shotgun.SG_USER["id"])

    def test_sync_jira_fields_to_sg_with_unmapped_status(self, mocked_sg):
        """A Jira status with no FPTR counterpart leaves the FPTR status alone."""

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        jira_issue.update(
            fields={
                "status": jira.resources.Status(None, None, raw={"name": "Unmapped"})
            }
        )

        self.assertTrue(
            handler._sync_jira_fields_to_sg(
                jira_issue, jira_issue.key, sg_task, ["status"]
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task", [["id", "is", sg_task["id"]]], ["sg_status_list"]
        )
        self.assertEqual(
            sg_task["sg_status_list"], mock_shotgun.SG_TASK["sg_status_list"]
        )

    def test_sync_jira_fields_to_sg_extracts_worklog_author(self, mocked_sg):
        """
        A worklog comment created by the bridge names its FPTR author, which is
        used to set the TimeLog user rather than the Jira worklog author.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        jira_worklog = bridge.jira.add_worklog(
            jira_issue,
            timeSpentSeconds=60,
            comment=handler._hook.compose_jira_worklog_comment(
                {"user": mock_shotgun.SG_USER, "description": "Some work"}
            ),
        )

        sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        sg_timelog["entity"] = sg_task
        sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_worklog.id)
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog)

        self.assertTrue(
            handler._sync_jira_fields_to_sg(
                jira_issue, jira_worklog.id, sg_timelog, ["comment"]
            )
        )

        sg_timelog = bridge.shotgun.find_one(
            "TimeLog", [["id", "is", sg_timelog["id"]]], ["description", "user"]
        )
        self.assertEqual(sg_timelog["description"], "Some work")
        self.assertEqual(sg_timelog["user"]["id"], mock_shotgun.SG_USER["id"])

    def test_sync_jira_fields_to_sg_when_value_conversion_raises(self, mocked_sg):
        """
        A hook raising while converting a Jira value is reported as a failed sync
        and leaves the FPTR entity untouched.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        with mock.patch.object(
            handler._hook,
            "get_sg_value_from_jira_value",
            side_effect=RuntimeError("boom"),
        ):
            self.assertFalse(
                handler._sync_jira_fields_to_sg(
                    jira_issue, jira_issue.key, sg_task, ["summary"]
                )
            )

        sg_task = bridge.shotgun.find_one(
            "Task", [["id", "is", sg_task["id"]]], ["content"]
        )
        self.assertEqual(sg_task["content"], mock_shotgun.SG_TASK["content"])

    # -------------------------------------------------------------------------------
    # Cascading worklog/comment sync
    # -------------------------------------------------------------------------------

    def test_sync_jira_worklogs_to_sg_when_timelogs_are_not_configured(self, mocked_sg):
        """
        Worklogs are only synced when TimeLog is part of the entity mapping, which
        is not the case in the default configuration.
        """

        handler, bridge = self._get_handler(mocked_sg)
        self._drop_entity_mapping(handler, "TimeLog")

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        bridge.jira.add_worklog(jira_issue, timeSpentSeconds=60)

        self.assertTrue(handler._sync_jira_worklogs_to_sg(jira_issue))
        self.assertEqual(bridge.shotgun.find("TimeLog", []), [])

    def test_sync_jira_worklogs_to_sg_without_a_synced_issue(self, mocked_sg):
        """
        A worklog on an Issue whose FPTR entity isn't flagged as synced can't be
        turned into a TimeLog.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue, sync_in_jira=False)
        bridge.jira.add_worklog(jira_issue, timeSpentSeconds=60)

        self.assertFalse(handler._sync_jira_worklogs_to_sg(jira_issue))
        self.assertEqual(bridge.shotgun.find("TimeLog", []), [])

    def test_sync_jira_worklogs_to_sg_reports_field_errors(self, mocked_sg):
        """
        A worklog missing one of the mapped Jira fields is reported, but the FPTR
        TimeLog is still created with the values that could be read.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        # no timeSpentSeconds on this worklog, which the TimeLog maps to "duration"
        bridge.jira.add_worklog(jira_issue, comment="Some work")

        self.assertFalse(handler._sync_jira_worklogs_to_sg(jira_issue))

        sg_timelogs = bridge.shotgun.find("TimeLog", [], ["description", "duration"])
        self.assertEqual(len(sg_timelogs), 1)
        self.assertEqual(sg_timelogs[0]["description"], "Some work")
        # the field that couldn't be read never made it to FPTR
        self.assertFalse(sg_timelogs[0]["duration"])

    def test_sync_jira_worklogs_to_sg_deletes_stale_timelogs(self, mocked_sg):
        """
        With deletion enabled from Jira, a FPTR TimeLog whose Jira worklog is gone
        is deleted; the ones still in Jira are kept.
        """

        handler, bridge = self._get_handler(
            mocked_sg, name="entities_generic_jira_to_sg_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        jira_worklog = bridge.jira.add_worklog(
            jira_issue, timeSpentSeconds=60, comment="Some work"
        )

        live_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        live_timelog["entity"] = sg_task
        live_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (
            jira_issue.key,
            jira_worklog.id,
        )
        self.add_to_sg_mock_db(bridge.shotgun, live_timelog)

        stale_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        stale_timelog["id"] = 2
        stale_timelog["entity"] = sg_task
        stale_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/999" % jira_issue.key
        self.add_to_sg_mock_db(bridge.shotgun, stale_timelog)

        self.assertTrue(handler._sync_jira_worklogs_to_sg(jira_issue))

        sg_timelogs = bridge.shotgun.find("TimeLog", [], [SHOTGUN_JIRA_ID_FIELD])
        self.assertEqual(len(sg_timelogs), 1)
        self.assertEqual(
            sg_timelogs[0][SHOTGUN_JIRA_ID_FIELD],
            "%s/%s" % (jira_issue.key, jira_worklog.id),
        )

    def test_sync_jira_comments_to_sg_when_notes_are_not_configured(self, mocked_sg):
        """Comments are only synced when Note is part of the entity mapping."""

        handler, bridge = self._get_handler(mocked_sg)
        self._drop_entity_mapping(handler, "Note")

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        bridge.jira.add_comment(jira_issue, "Some comment")

        self.assertTrue(handler._sync_jira_comments_to_sg(jira_issue))
        self.assertEqual(bridge.shotgun.find("Note", []), [])

    def test_sync_jira_comments_to_sg_reports_field_errors(self, mocked_sg):
        """
        A comment deleted between being listed and being read is reported, and the
        Note it would have filled is left empty.
        """

        handler, bridge = self._get_handler(mocked_sg)

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        bridge.jira.add_comment(jira_issue, "Some comment")

        with mock.patch.object(bridge.jira, "comment", return_value=None):
            self.assertFalse(handler._sync_jira_comments_to_sg(jira_issue))

        sg_notes = bridge.shotgun.find("Note", [], ["content"])
        self.assertEqual(len(sg_notes), 1)
        self.assertIsNone(sg_notes[0]["content"])

    def test_sync_jira_comments_to_sg_deletes_stale_notes(self, mocked_sg):
        """
        With deletion enabled from Jira, a FPTR Note whose Jira comment is gone is
        deleted; the ones still in Jira are kept.
        """

        handler, bridge = self._get_handler(
            mocked_sg, name="entities_generic_jira_to_sg_deletion"
        )

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
        jira_comment = bridge.jira.add_comment(
            jira_issue, "Some comment", author=mock_jira.JIRA_USER
        )

        live_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        live_note["tasks"] = [sg_task]
        live_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_comment.id)
        self.add_to_sg_mock_db(bridge.shotgun, live_note)

        stale_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        stale_note["id"] = 2
        stale_note["tasks"] = [sg_task]
        stale_note[SHOTGUN_JIRA_ID_FIELD] = "%s/999" % jira_issue.key
        self.add_to_sg_mock_db(bridge.shotgun, stale_note)

        self.assertTrue(handler._sync_jira_comments_to_sg(jira_issue))

        sg_notes = bridge.shotgun.find("Note", [], [SHOTGUN_JIRA_ID_FIELD])
        self.assertEqual(len(sg_notes), 1)
        self.assertEqual(
            sg_notes[0][SHOTGUN_JIRA_ID_FIELD],
            "%s/%s" % (jira_issue.key, jira_comment.id),
        )
