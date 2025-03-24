# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os

import mock
from mock_shotgun import SG_ASSET, SG_RETIRED_TIMELOG, SG_TASK, SG_USER
from shotgun_api3.lib import mockgun
from test_base import TestBase

import sg_jira


# Mock Flow Production Tracking with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
class TestShotgunSession(TestBase):
    """ """

    def setUp(self):
        """Test setup."""
        super(TestShotgunSession, self).setUp()

        # Set up the PTR database
        self.set_sg_mock_schema(
            os.path.join(
                self._fixtures_path,
                "schemas",
                "sg-jira",
            )
        )

        self.mock_jira_session_bases()

    def _get_sg_session(self, mocked_sg):
        """Return a PTR session object."""
        mocked_sg.return_value = mockgun.Shotgun(
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

        self.add_to_sg_mock_db(sg_session, SG_TASK)
        consolidated_task = sg_session.consolidate_entity(
            {"type": SG_TASK["type"], "id": SG_TASK["id"]}
        )

        self.assertEqual(consolidated_task["content"], SG_TASK["content"])
        self.assertEqual(consolidated_task["name"], SG_TASK["content"])
        self.assertEqual(consolidated_task["task_assignees"], SG_TASK["task_assignees"])
        self.assertEqual(consolidated_task["project"]["id"], SG_TASK["project"]["id"])
        self.assertNotIn("description", consolidated_task)

    def test_consolidate_human_user_entity(self, mocked_sg):
        """Test the HumanUser entity consolidation"""

        sg_session = self._get_sg_session(mocked_sg)

        self.add_to_sg_mock_db(sg_session, SG_USER)
        consolidated_user = sg_session.consolidate_entity(
            {"type": SG_USER["type"], "id": SG_USER["id"]}
        )

        # Consolidate HumanUser must have email and name fields
        self.assertEqual(consolidated_user["email"], SG_USER["email"])
        self.assertEqual(consolidated_user["name"], SG_USER["name"])
        self.assertNotIn("project", consolidated_user)

    def test_consolidate_asset_entity(self, mocked_sg):
        """Test the Asset entity consolidation"""

        sg_session = self._get_sg_session(mocked_sg)

        self.add_to_sg_mock_db(sg_session, SG_ASSET)
        consolidated_asset = sg_session.consolidate_entity(
            {"type": SG_ASSET["type"], "id": SG_ASSET["id"]}
        )

        # Consolidate Asset must have code and project fields
        self.assertEqual(consolidated_asset["code"], SG_ASSET["code"])
        self.assertEqual(consolidated_asset["project"]["id"], SG_TASK["project"]["id"])

    def test_consolidate_entity_extra_fields(self, mocked_sg):
        """Test the task entity consolidation with extra fields"""

        sg_session = self._get_sg_session(mocked_sg)

        self.add_to_sg_mock_db(sg_session, SG_TASK)
        consolidated_task = sg_session.consolidate_entity(
            {"type": SG_TASK["type"], "id": SG_TASK["id"]}, fields=["description"]
        )

        self.assertIn("description", consolidated_task)
        self.assertEqual(consolidated_task["description"], SG_TASK["description"])

    def test_consolidate_retired_entity_1(self, mocked_sg):
        """Test the retired entity consolidation"""

        sg_session = self._get_sg_session(mocked_sg)

        self.add_to_sg_mock_db(sg_session, SG_RETIRED_TIMELOG)
        consolidated_timelog = sg_session.consolidate_entity(
            {"type": SG_RETIRED_TIMELOG["type"], "id": SG_RETIRED_TIMELOG["id"]},
            retired_only=True,
        )

        self.assertEqual(consolidated_timelog["id"], SG_RETIRED_TIMELOG["id"])

    def test_consolidate_retired_entity_2(self, mocked_sg):
        """Test the retired entity consolidation (missing flag)"""

        sg_session = self._get_sg_session(mocked_sg)

        self.add_to_sg_mock_db(sg_session, SG_RETIRED_TIMELOG)
        consolidated_timelog = sg_session.consolidate_entity(
            {"type": SG_RETIRED_TIMELOG["type"], "id": SG_RETIRED_TIMELOG["id"]},
        )

        self.assertEqual(consolidated_timelog, None)
