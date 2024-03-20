# -*- coding: utf-8 -*-
# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import mock

from sg_jira.constants import SHOTGUN_JIRA_ID_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD
from sg_jira.constants import SHOTGUN_JIRA_URL_FIELD

from test_sync_base import TestSyncBase
from mock_jira import JIRA_PROJECT_KEY, JIRA_PROJECT, JIRA_USER

# A list of Shotgun Projects
SG_PROJECTS = [
    {
        "id": 1,
        "name": "Sync",
        "type": "Project",
        SHOTGUN_JIRA_ID_FIELD: JIRA_PROJECT_KEY,
    }
]

SG_USERS = [
    {
        "id": 1,
        "type": "HumanUser",
        "login": "ford.prefect",
        "sg_jira_account_id": JIRA_USER["accountId"],
    },
]


# Mock Shotgun with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
class TestHierarchySyncer(TestSyncBase):
    """
    Test hierarchy syncer example.
    """

    def test_shotgun_links_sync(self, mocked_sg):
        """
        Test syncing links from PTR to Jira.
        """
        syncer, bridge = self._get_syncer(mocked_sg, name="asset_hierarchy")
        bridge.jira.set_projects([JIRA_PROJECT])
        issue = bridge.jira.create_issue({})
        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECTS)
        synced_task = {
            "type": "Task",
            "id": 3,
            "content": "Task One/2",
            "project": SG_PROJECTS[0],
            SHOTGUN_JIRA_ID_FIELD: issue.key,
            SHOTGUN_SYNC_IN_JIRA_FIELD: True,
        }
        sg_asset = {
            "project": SG_PROJECTS[0],
            "type": "Asset",
            "id": 1,
            "code": "Foo",
            "description": "I'm Foo !",
            "tasks": [],
            SHOTGUN_SYNC_IN_JIRA_FIELD: True,
        }
        self.add_to_sg_mock_db(bridge.shotgun, sg_asset)
        self.add_to_sg_mock_db(bridge.shotgun, synced_task)
        self.add_to_sg_mock_db(bridge.shotgun, SG_USERS)

        self.assertTrue(
            bridge.sync_in_jira(
                "asset_hierarchy",
                "Asset",
                1,
                {
                    "user": {"type": "HumanUser", "id": 1},
                    "project": {"type": "Project", "id": 2},
                    "meta": {
                        "entity_id": 1,
                        "removed": [],
                        "attribute_name": "tasks",
                        "entity_type": "Asset",
                        "field_data_type": "multi_entity",
                        "added": [synced_task],
                        "type": "attribute_change",
                    },
                },
            )
        )
        updated_asset = bridge.shotgun.find_one(
            "Asset",
            [["id", "is", sg_asset["id"]]],
            [SHOTGUN_JIRA_ID_FIELD, SHOTGUN_JIRA_URL_FIELD],
        )
        # An Issue should have been created for the Asset
        self.assertIsNotNone(updated_asset[SHOTGUN_JIRA_ID_FIELD])

        # load the asset issue
        issue = bridge.jira.issue(updated_asset[SHOTGUN_JIRA_ID_FIELD])

        # make sure we're setting the Jira URL and it's what we expect
        self.assertIsNotNone(updated_asset[SHOTGUN_JIRA_URL_FIELD])
        expected_url = {"name": "View in Jira", "url": issue.permalink()}
        self.assertEqual(updated_asset[SHOTGUN_JIRA_URL_FIELD], expected_url)

        # Should return False because the link is already there (no update)
        self.assertFalse(
            bridge.sync_in_jira(
                "asset_hierarchy",
                "Asset",
                1,
                {
                    "user": {"type": "HumanUser", "id": 1},
                    "project": {"type": "Project", "id": 2},
                    "meta": {
                        "entity_id": 1,
                        "removed": [],
                        "attribute_name": "tasks",
                        "entity_type": "Asset",
                        "field_data_type": "multi_entity",
                        "added": [synced_task],
                        "type": "attribute_change",
                    },
                },
            )
        )

        # Should return True because a link is deleted
        self.assertTrue(
            bridge.sync_in_jira(
                "asset_hierarchy",
                "Asset",
                1,
                {
                    "user": {"type": "HumanUser", "id": 1},
                    "project": {"type": "Project", "id": 2},
                    "meta": {
                        "entity_id": 1,
                        "removed": [synced_task],
                        "attribute_name": "tasks",
                        "entity_type": "Asset",
                        "field_data_type": "multi_entity",
                        "added": [],
                        "type": "attribute_change",
                    },
                },
            )
        )
        # Should return False because a link is already deleted (no update)
        self.assertFalse(
            bridge.sync_in_jira(
                "asset_hierarchy",
                "Asset",
                1,
                {
                    "user": {"type": "HumanUser", "id": 1},
                    "project": {"type": "Project", "id": 2},
                    "meta": {
                        "entity_id": 1,
                        "removed": [synced_task],
                        "attribute_name": "tasks",
                        "entity_type": "Asset",
                        "field_data_type": "multi_entity",
                        "added": [],
                        "type": "attribute_change",
                    },
                },
            )
        )
