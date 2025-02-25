# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
import copy
import jira
import mock
import os

from shotgun_api3.lib import mockgun
from test_sync_base import TestSyncBase
import mock_jira
import mock_shotgun

import sg_jira
from sg_jira.constants import (SHOTGUN_JIRA_ID_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD, SHOTGUN_JIRA_URL_FIELD, JIRA_SYNC_IN_FPTR_FIELD,
                               JIRA_SHOTGUN_TYPE_FIELD, JIRA_SHOTGUN_ID_FIELD, JIRA_SHOTGUN_URL_FIELD)


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

    def _mock_sg_data(self, sg_instance, jira_issue=None, sync_in_jira=True):
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
        self.add_to_sg_mock_db(sg_instance, mocked_sg_task)

        return mocked_sg_task

    def _mock_jira_data(self, bridge, sg_entity=None, issue_type_name="Task", sync_in_fptr="True"):
        """
        Helper method to mock Jira data.
        We can't call it in the `setUp` method as we need the bridge instance...
        """
        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        if sg_entity:
            jira_issue = bridge.jira.create_issue({
                "issuetype": bridge.jira.issue_type_by_name(issue_type_name),
                bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_ID_FIELD.lower()): sg_entity["id"],
                bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_TYPE_FIELD.lower()): sg_entity["type"],
                bridge.jira.get_jira_issue_field_id(JIRA_SYNC_IN_FPTR_FIELD.lower()): jira.resources.CustomFieldOption(None, None, {"value": sync_in_fptr}),
            })
            return jira_issue
        return bridge.jira.create_issue(
            fields={
                "issuetype": bridge.jira.issue_type_by_name(issue_type_name),
                bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_ID_FIELD.lower()): "",
                bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_TYPE_FIELD.lower()): "",
                bridge.jira.get_jira_issue_field_id(JIRA_SYNC_IN_FPTR_FIELD.lower()): jira.resources.CustomFieldOption(None, None, {"value": sync_in_fptr}),
            }
        )

    def _mock_jira_issue_event(self, jira_issue, jira_event):
        """Helper method to mock Jira issue event."""

        mocked_jira_event = copy.deepcopy(jira_event)
        mocked_jira_event["issue"] = {
            "id": jira_issue.key,
            "key": jira_issue.key
        }
        return mocked_jira_event

    def _check_jira_issue(self, bridge, sg_entity, sync_in_fptr=None):
        """Helper method to check that a Jira issue is correctly created."""

        # Jira Issue should be created
        jira_issue = bridge.jira.issue(sg_entity[SHOTGUN_JIRA_ID_FIELD])
        self.assertIsNotNone(jira_issue)

        # its "Sync in FPTR" field should be set to "True"
        sync_in_fptr_jira_field_id = bridge.jira.get_jira_issue_field_id(JIRA_SYNC_IN_FPTR_FIELD.lower())
        self.assertEqual(jira_issue.get_field(sync_in_fptr_jira_field_id).value, sync_in_fptr)

        # all its FPTR fields should be filled with the Task data
        sg_type_jira_field_id = bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_TYPE_FIELD.lower())
        self.assertEqual(jira_issue.get_field(sg_type_jira_field_id), sg_entity["type"])

        sg_id_jira_field_id = bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_ID_FIELD.lower())
        self.assertEqual(jira_issue.get_field(sg_id_jira_field_id), str(sg_entity["id"]))

        sg_url_jira_field_id = bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_URL_FIELD.lower())
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
        self.assertRaises(RuntimeError, self._get_syncer, mocked_sg, "entities_generic_bad_sg_entity_formatting")
        # "jira_issue_type" key must be defined in the entity_mapping dictionary
        self.assertRaises(RuntimeError, self._get_syncer, mocked_sg, "entities_generic_bad_jira_issue_type_formatting")

    def test_bad_settings_formatting_for_field_mapping(self, mocked_sg):
        """Test all the use cases where the entity field mappings setting is not correctly formatted."""
        # "field_mapping" key must be defined in the entity_mapping dictionary
        self.assertRaises(RuntimeError, self._get_syncer, mocked_sg, "entities_generic_bad_fields_formatting")
        # "sg_field" key must be defined in the field_mapping dictionary
        self.assertRaises(
            RuntimeError, self._get_syncer, mocked_sg,"entities_generic_bad_fields_formatting_missing_sg_field_key"
        )
        # "jira_field" key must be defined in the field_mapping dictionary
        self.assertRaises(
            RuntimeError, self._get_syncer, mocked_sg,"entities_generic_bad_fields_formatting_missing_jira_field_key"
        )

    def test_bad_settings_formatting_for_status_mapping(self, mocked_sg):
        """Test all the use cases where the status field mappings setting is not correctly formatted."""
        # "sg_field" key must be defined in the field_mapping dictionary
        self.assertRaises(
            RuntimeError, self._get_syncer, mocked_sg,"entities_generic_bad_status_formatting_missing_sg_field_key"
        )
        # "mapping" key must be defined in the field_mapping dictionary
        self.assertRaises(
            RuntimeError, self._get_syncer, mocked_sg,"entities_generic_bad_status_formatting_missing_mapping_key"
        )

    def test_project_in_entity_mapping(self, mocked_sg):
        """Test that a FPTR project entity cannot be used in the entity mapping."""
        self.assertRaises(RuntimeError, self._get_syncer, mocked_sg, "entities_generic_with_project")

    def test_fptr_missing_fields_in_schema(self, mocked_sg):
        """Test that the FPTR entities used in the entity mapping are correctly setup in FPTR"""

        # SHOTGUN_JIRA_ID_FIELD field must have been created for the FPTR entity
        self.assertRaises(
            RuntimeError, self._get_syncer, mocked_sg, "entities_generic_sg_entity_with_missing_field_in_schema"
        )
        # FPTR field associated to Jira "assignee" field must be an entity/multi-entity field
        self.assertRaises(ValueError, self._get_syncer, mocked_sg, "entities_generic_bad_assignee_field_type")
        # FPTR field associated to Jira "assignee" field must be an entity/multi-entity field supporting HumanUser
        self.assertRaises(ValueError, self._get_syncer, mocked_sg, "entities_generic_bad_assignee_field_entity_type")


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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_bad_jira_issue_type")

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
            [SHOTGUN_JIRA_URL_FIELD, SHOTGUN_JIRA_ID_FIELD, "content", "sg_description"]
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
            [SHOTGUN_JIRA_URL_FIELD, SHOTGUN_JIRA_ID_FIELD, "content", "sg_description"]
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
            [SHOTGUN_JIRA_URL_FIELD, SHOTGUN_JIRA_ID_FIELD, "content", "sg_description"]
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
        self.assertNotEqual(jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"])

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
            [SHOTGUN_JIRA_URL_FIELD, SHOTGUN_JIRA_ID_FIELD, "content", "sg_description"]
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
        self.assertNotEqual(jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"])

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
            [SHOTGUN_JIRA_URL_FIELD, SHOTGUN_JIRA_ID_FIELD, "content", "sg_description"]
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
            [SHOTGUN_JIRA_ID_FIELD]
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
            mocked_sg_task["type"],
            mocked_sg_task["id"],
            {"entity": mocked_sg_asset}
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
        self.assertNotEqual(jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"])
        self.assertNotEqual(jira_issue.fields.description, mocked_sg.SG_TASK["due_date"])

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
            [SHOTGUN_JIRA_URL_FIELD, SHOTGUN_JIRA_ID_FIELD, "content", "sg_description"]
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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_status_both_way")

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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_status_sg_to_jira")

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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_status_jira_to_sg")

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

    def test_fptr_to_jira_sync_new_timelog_not_linked_to_a_synced_entity(self, mocked_sg):
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
            "TimeLog",
            [["id", "is", mocked_sg_timelog["id"]]],
            [SHOTGUN_JIRA_ID_FIELD]
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
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_worklog.id)
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
        self.assertEqual(jira_worklog.timeSpentSeconds, mock_shotgun.SG_TIMELOG["duration"] * 60)

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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_both_way_deletion")

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

    def test_fptr_to_jira_delete_timelog_linked_to_synced_entity_both_way_sync_deletion(self, mocked_sg):
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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_both_way_deletion")

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(jira_issue)
        self.assertEqual(len(bridge._jira.worklogs(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["__retired"] = True
        mocked_sg_timelog["entity"] = [sg_mocked_task]
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_worklog.id)
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

    def test_fptr_to_jira_delete_timelog_linked_to_synced_entity_sg_to_jira_sync_deletion(self, mocked_sg):
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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_sg_to_jira_deletion")

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(jira_issue)
        self.assertEqual(len(bridge._jira.worklogs(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["__retired"] = True
        mocked_sg_timelog["entity"] = [sg_mocked_task]
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_worklog.id)
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

    def test_fptr_to_jira_delete_timelog_linked_to_synced_entity_jira_to_sg_sync_deletion(self, mocked_sg):
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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_jira_to_sg_deletion")

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_worklog = bridge.jira.add_worklog(jira_issue)
        self.assertEqual(len(bridge._jira.worklogs(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_timelog = copy.deepcopy(mock_shotgun.SG_TIMELOG)
        mocked_sg_timelog["__retired"] = True
        mocked_sg_timelog["entity"] = [sg_mocked_task]
        mocked_sg_timelog[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_worklog.id)
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
            "Note",
            [["id", "is", mocked_sg_note["id"]]],
            [SHOTGUN_JIRA_ID_FIELD]
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
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_comment.id)
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

    # def test_fptr_to_jira_sync_existing_note_remove_linked_entity(self, mocked_sg):
    #     """
    #     TODO
    #
    #     Test environment:
    #     - the entity/field mapping has been done correctly in the settings
    #     - the entity is flagged as ready to sync in FPTR
    #     - the sync direction is not set, meaning that it will be both_way by default
    #     - the Comment already exists in Jira and is correctly associated to the FPTR entity
    #     Expected result:
    #     - the Jira comment should be deleted
    #     """
    #
    #     syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
    #
    #     jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
    #     jira_comment = bridge.jira.add_comment(jira_issue, "created in Jira")
    #     mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)
    #
    #     mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
    #     mocked_sg_note["tasks"] = []
    #     mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_comment.id)
    #     self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_note)
    #
    #     mocked_sg_event = copy.deepcopy(mock_shotgun.SG_NOTE_CHANGE_EVENT)
    #     mocked_sg_event["meta"]["attribute_name"] = "tasks"
    #     mocked_sg_event["meta"]["removed"] = [mocked_sg_task]
    #
    #     self.assertTrue(
    #         bridge.sync_in_jira(
    #             self.HANDLER_NAME,
    #             "Note",
    #             mock_shotgun.SG_NOTE["id"],
    #             mocked_sg_event,
    #         )
    #     )
    #
    #     self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 0)

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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_both_way_deletion")

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

    def test_fptr_to_jira_delete_note_linked_to_synced_entity_both_way_sync_deletion(self, mocked_sg):
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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_both_way_deletion")

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "my comment")
        self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["__retired"] = True
        mocked_sg_note["tasks"] = [sg_mocked_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_comment.id)
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

    def test_fptr_to_jira_delete_note_linked_to_synced_entity_sg_to_jira_sync_deletion(self, mocked_sg):
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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_sg_to_jira_deletion")

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "my comment")
        self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["__retired"] = True
        mocked_sg_note["tasks"] = [sg_mocked_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_comment.id)
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

    def test_fptr_to_jira_delete_note_linked_to_synced_entity_jira_to_sg_sync_deletion(self, mocked_sg):
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

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_jira_to_sg_deletion")

        jira_issue = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_TASK)
        jira_comment = bridge.jira.add_comment(jira_issue, "my comment")
        self.assertEqual(len(bridge._jira.comments(jira_issue.key)), 1)

        sg_mocked_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_sg_note = copy.deepcopy(mock_shotgun.SG_NOTE)
        mocked_sg_note["__retired"] = True
        mocked_sg_note["tasks"] = [sg_mocked_task]
        mocked_sg_note[SHOTGUN_JIRA_ID_FIELD] = "%s/%s" % (jira_issue.key, jira_comment.id)
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
                self.HANDLER_NAME,
                "Issue",
                "FAKED-01",
                bad_webhook_event
            )
        )

    def test_jira_to_fptr_missing_jira_entity(self, mocked_sg):
        """The event will be rejected if the jira entity is missing."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME,
                "Issue",
                "FAKED-01",
                mock_jira.ISSUE_CREATED_PAYLOAD
            )
        )

    def test_jira_to_fptr_missing_changelog(self, mocked_sg):
        """The event will be rejected if the changelog is missing."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge)
        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD)

        del mocked_jira_event["changelog"]

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME,
                "Issue",
                "FAKED-01",
                mocked_jira_event
            )
        )

    def test_jira_to_fptr_issue_type_not_supported(self, mocked_sg):
        """Reject the event if the issue type is not supported."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        bridge.jira.set_projects([mock_jira.JIRA_PROJECT])
        jira_issue = bridge.jira.create_issue(
            fields={
                "issuetype": bridge.jira.issue_type_by_name("BadIssueType")
            }
        )
        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD)

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME,
                "Issue",
                jira_issue.key,
                mocked_jira_event
            )
        )

    # TODO: enable the test when the worklog deletion will be enabled

    # def test_jira_to_fptr_missing_issue_id(self, mocked_sg):
    #     """Reject the event if the issue id is missing from the worklog/comment payload."""
    #
    #     missing_id_event = copy.deepcopy(mock_jira.WORKLOG_DELETED_PAYLOAD)
    #     del missing_id_event["worklog"]["issueId"]
    #
    #     syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)
    #
    #     self.assertFalse(
    #         bridge.sync_in_shotgun(
    #             self.HANDLER_NAME,
    #             "Issue",
    #             "FAKED-01",
    #             missing_id_event
    #         )
    #     )

    # TODO: add a test against deletion sync flag check

    def test_jira_to_fptr_bad_sync_direction(self, mocked_sg):
        """Reject the event if the sync direction is configured to work from FPTR to Jira."""

        syncer, bridge = self._get_syncer(mocked_sg, name="entities_generic_sg_to_jira")

        jira_issue = self._mock_jira_data(bridge)
        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD)

        self.assertFalse(
            bridge.sync_in_shotgun(
                "entities_generic_sg_to_jira",
                "Issue",
                jira_issue.key,
                mocked_jira_event
            )
        )

    def test_jira_to_fptr_jira_project_not_linked_to_sg_project(self, mocked_sg):
        """Reject the event if the sync direction is configured to work from FPTR to Jira."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge)
        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD)

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME,
                "Issue",
                jira_issue.key,
                mocked_jira_event
            )
        )

    def test_jira_to_fptr_entity_not_flagged_as_sync(self, mocked_sg):
        """Reject the event if the Jira entity is not flagged as synced."""

        syncer, bridge = self._get_syncer(mocked_sg, name=self.HANDLER_NAME)

        jira_issue = self._mock_jira_data(bridge, sync_in_fptr="False")
        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD)

        self._mock_sg_data(bridge.shotgun)

        self.assertFalse(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME,
                "Issue",
                jira_issue.key,
                mocked_jira_event
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
        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD)

        self._mock_sg_data(bridge.shotgun)

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]]
        )

        self.assertEqual(sg_task, None)

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME,
                "Issue",
                jira_issue.key,
                mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            [SHOTGUN_JIRA_ID_FIELD, SHOTGUN_JIRA_URL_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD]
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
        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD)

        self._mock_sg_data(bridge.shotgun)

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]]
        )

        self.assertEqual(sg_task, None)

        self.assertTrue(
            bridge.sync_in_shotgun(
                "entities_generic_both_way",
                "Issue",
                jira_issue.key,
                mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            [SHOTGUN_JIRA_ID_FIELD, SHOTGUN_JIRA_URL_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD]
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
        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_CREATED_PAYLOAD)

        self._mock_sg_data(bridge.shotgun)

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]]
        )

        self.assertEqual(sg_task, None)

        self.assertTrue(
            bridge.sync_in_shotgun(
                "entities_generic_jira_to_sg",
                "Issue",
                jira_issue.key,
                mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            [SHOTGUN_JIRA_ID_FIELD, SHOTGUN_JIRA_URL_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD]
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

        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)

        self.assertNotEqual(jira_issue.fields.summary, mocked_sg.SG_TASK["content"])
        self.assertNotEqual(jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"])

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME,
                "Issue",
                jira_issue.key,
                mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            ["content", "sg_description"]
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
        bridge.jira.add_comment(jira_issue, "jira comment body")
        bridge.jira.add_worklog(jira_issue, timeSpentSeconds=0, comment="jira worklog body")

        mocked_sg_task = self._mock_sg_data(bridge.shotgun, jira_issue=jira_issue)

        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)
        mocked_jira_event["changelog"]["items"][0]["field"] = "Sync In FPTR"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "customfield_11504"

        sg_notes = bridge.shotgun.find(
            "Note",
            [["tasks", "is", mocked_sg_task]]
        )
        self.assertEqual(len(sg_notes), 0)

        sg_timelogs = bridge.shotgun.find(
            "TimeLog",
            [["entity", "is", mocked_sg_task]]
        )
        self.assertEqual(len(sg_timelogs), 0)

        self.assertNotEqual(jira_issue.fields.summary, mocked_sg.SG_TASK["content"])
        self.assertNotEqual(jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"])

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME,
                "Issue",
                jira_issue.key,
                mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            ["content", "sg_description"]
        )

        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])

        sg_notes = bridge.shotgun.find(
            "Note",
            [["tasks", "is", mocked_sg_task]]
        )
        self.assertEqual(len(sg_notes), 1)

        sg_timelogs = bridge.shotgun.find(
            "TimeLog",
            [["entity", "is", mocked_sg_task]]
        )
        self.assertEqual(len(sg_timelogs), 1)

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

        jira_epic = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_ASSET, sync_in_fptr="False")
        jira_issue.update(fields={"parent": jira_epic})

        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)
        mocked_jira_event["changelog"]["items"][0]["field"] = "parent"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "parent"

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME,
                "Issue",
                jira_issue.key,
                mocked_jira_event
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

        jira_epic = self._mock_jira_data(bridge, sg_entity=mock_shotgun.SG_ASSET, issue_type_name="Epic")
        mocked_sg_asset = copy.deepcopy(mock_shotgun.SG_ASSET)
        mocked_sg_asset[SHOTGUN_JIRA_ID_FIELD] = jira_epic.key
        mocked_sg_asset[SHOTGUN_SYNC_IN_JIRA_FIELD] = True
        self.add_to_sg_mock_db(bridge.shotgun, mocked_sg_asset)

        jira_issue.update(fields={"parent": jira_epic})

        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)
        mocked_jira_event["changelog"]["items"][0]["field"] = "parent"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "parent"

        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", mock_shotgun.SG_TASK["id"]]],
            ["entity"]
        )
        self.assertEqual(sg_task["entity"], None)

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME,
                "Issue",
                jira_issue.key,
                mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", mock_shotgun.SG_TASK["id"]]],
            ["entity"]
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

        mocked_jira_event = self._mock_jira_issue_event(jira_issue, mock_jira.ISSUE_UPDATED_PAYLOAD)
        mocked_jira_event["changelog"]["items"][0]["field"] = "Sync In FPTR"
        mocked_jira_event["changelog"]["items"][0]["fieldId"] = "customfield_11504"

        self.assertNotEqual(jira_issue.fields.summary, mocked_sg.SG_TASK["content"])
        self.assertNotEqual(jira_issue.fields.description, mocked_sg.SG_TASK["sg_description"])
        self.assertNotEqual(jira_issue.fields.description, mocked_sg.SG_TASK["due_date"])

        self.assertTrue(
            bridge.sync_in_shotgun(
                self.HANDLER_NAME,
                "Issue",
                jira_issue.key,
                mocked_jira_event
            )
        )

        sg_task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", mock_shotgun.SG_TASK["id"]]],
            [SHOTGUN_JIRA_URL_FIELD, SHOTGUN_JIRA_ID_FIELD, "content", "sg_description"]
        )
        jira_issue = bridge.jira.issue(jira_issue.key)

        # direction for this field is empty aka "both_way"
        self.assertEqual(jira_issue.fields.summary, sg_task["content"])
        # direction for this field is "sg_to_jira"
        self.assertEqual(jira_issue.fields.description, sg_task["sg_description"])
        # direction for this field is "jira_to_sg"
        self.assertNotEqual(jira_issue.fields.duedate, mocked_sg.SG_TASK["due_date"])