# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import mock
import os

import sg_jira
from test_base import TestBase
from test_sync_base import ExtMockgun


# Mock Shotgun with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
class TestShotgunSession(TestBase):
    """ """

    def setUp(self):
        """Test setup."""
        super(TestShotgunSession, self).setUp()

        # Set up the FPT database
        self.set_sg_mock_schema(
            os.path.join(
                self._fixtures_path,
                "schemas",
                "sg-jira",
            )
        )

        # Mock up some data
        self.project = {
            "id": 1,
            "name": "Sync",
            "type": "Project",
        }
        self.user = {
            "id": 1,
            "type": "HumanUser",
            "login": "ford.prefect",
            "email": "ford.prefect@mail.com",
            "name": "Ford Prefect",
        }
        self.task = {
            "type": "Task",
            "id": 3,
            "content": "Task 1",
            "project": self.project,
            "task_assignees": [self.user],
            "description": "Task Description",
        }
        self.retired_task = {
            "type": "Task",
            "id": 4,
            "content": "Retired Task",
            "project": self.project,
            "task_assignees": [self.user],
            "description": "Task Description",
            "__retired": True,
        }
        self.asset = {
            "type": "Asset",
            "id": 1,
            "code": "Asset 1",
            "project": self.project,
        }

    def _get_sg_session(self, mocked_sg):
        """Return a Shotgun session object."""
        mocked_sg.return_value = ExtMockgun(
            "https://mocked.my.com",
            "Ford Prefect",
            "xxxxxxxxxx",
        )
        bridge = sg_jira.Bridge.get_bridge(
            os.path.join(self._fixtures_path, "settings.py")
        )
        return bridge.shotgun

    def test_consolidate_task_entity(self, mocked_sg):
        """Test the task entity consolidation"""

        sg_session = self._get_sg_session(mocked_sg)

        self.add_to_sg_mock_db(sg_session, self.task)
        consolidated_task = sg_session.consolidate_entity(
            {"type": self.task["type"], "id": self.task["id"]}
        )

        self.assertEqual(consolidated_task["content"], self.task["content"])
        self.assertEqual(consolidated_task["name"], self.task["content"])
        self.assertEqual(
            consolidated_task["task_assignees"], self.task["task_assignees"]
        )
        self.assertEqual(consolidated_task["project"], self.task["project"])
        self.assertNotIn("description", consolidated_task)

    def test_consolidate_human_user_entity(self, mocked_sg):
        """Test the HumanUser entity consolidation"""

        sg_session = self._get_sg_session(mocked_sg)

        self.add_to_sg_mock_db(sg_session, self.user)
        consolidated_user = sg_session.consolidate_entity(
            {"type": self.user["type"], "id": self.user["id"]}
        )

        # Consolidate HumanUser must have email and name fields
        self.assertEqual(consolidated_user["email"], self.user["email"])
        self.assertEqual(consolidated_user["name"], self.user["name"])
        self.assertNotIn("project", consolidated_user)

    def test_consolidate_asset_entity(self, mocked_sg):
        """Test the Asset entity consolidation"""

        sg_session = self._get_sg_session(mocked_sg)

        self.add_to_sg_mock_db(sg_session, self.asset)
        consolidated_asset = sg_session.consolidate_entity(
            {"type": self.asset["type"], "id": self.asset["id"]}
        )

        # Consolidate HumanUser must have email and name fields
        self.assertEqual(consolidated_asset["code"], self.asset["code"])
        self.assertEqual(consolidated_asset["project"], self.task["project"])

    def test_consolidate_entity_extra_fields(self, mocked_sg):
        """Test the task entity consolidation with extra fields"""

        sg_session = self._get_sg_session(mocked_sg)

        self.add_to_sg_mock_db(sg_session, self.task)
        consolidated_task = sg_session.consolidate_entity(
            {"type": self.task["type"], "id": self.task["id"]}, fields=["description"]
        )

        self.assertIn("description", consolidated_task)
        self.assertEqual(consolidated_task["description"], self.task["description"])

    def test_consolidate_retired_entity_1(self, mocked_sg):
        """Test the retired entity consolidation"""

        sg_session = self._get_sg_session(mocked_sg)

        self.add_to_sg_mock_db(sg_session, self.retired_task)
        consolidated_task = sg_session.consolidate_entity(
            {"type": self.retired_task["type"], "id": self.retired_task["id"]},
            retired_only=True,
        )

        self.assertEqual(consolidated_task["content"], self.retired_task["content"])

    def test_consolidate_retired_entity_2(self, mocked_sg):
        """Test the retired entity consolidation (missing flag)"""

        sg_session = self._get_sg_session(mocked_sg)

        self.add_to_sg_mock_db(sg_session, self.retired_task)
        consolidated_task = sg_session.consolidate_entity(
            {"type": self.retired_task["type"], "id": self.retired_task["id"]},
        )

        self.assertEqual(consolidated_task, None)
