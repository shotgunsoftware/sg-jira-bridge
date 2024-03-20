# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import mock

from sg_jira.handlers import SyncHandler
from mock_jira import JIRA_USER, JIRA_PROJECT, JIRA_PROJECT_KEY
from test_sync_base import TestSyncBase


# Mock Flow Production Tracking with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
class TestSyncHandler(TestSyncBase):
    """SyncHandler test class"""

    def setUp(self):
        """Test setup."""

        super(TestSyncHandler, self).setUp()

        # Mock up some data
        self.user = {
            "id": 1,
            "type": "HumanUser",
            "login": "ford.prefect",
            "email": JIRA_USER["emailAddress"],
            "name": "Ford Prefect",
            "sg_jira_account_id": JIRA_USER["accountId"],
        }

    def _get_handler(self, mocked_sg):
        """Helper method to get the handler"""
        syncer, bridge = self._get_syncer(mocked_sg)
        return SyncHandler(syncer)

    def test_get_jira_cloud_user(self, mocked_sg):
        """Test the method to get the Jira cloud user from its email address"""

        jira_user = self._test_get_jira_user(True, mocked_sg)
        self.assertNotIn("name", jira_user)
        self.assertEqual(jira_user["accountId"], JIRA_USER["accountId"])

    def test_get_jira_server_user(self, mocked_sg):
        """Test the method to get the Jira server user fron its email address"""
        jira_user = self._test_get_jira_user(False, mocked_sg)
        self.assertNotIn("accountId", jira_user)
        self.assertEqual(jira_user["name"], JIRA_USER["name"])

    def _test_get_jira_user(self, is_jira_cloud, mocked_sg):
        """Generic method to get the Jira user from its email address"""

        # Force JIRA cloud or not on the session, which will impact how the
        # webhook data is interpreted.
        patcher = mock.patch(
            "sg_jira.jira_session.JiraSession.is_jira_cloud",
            new_callable=mock.PropertyMock,
            return_value=is_jira_cloud,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        handler = self._get_handler(mocked_sg)

        # add the faked Jira Project
        handler._jira.set_projects([JIRA_PROJECT])
        jira_project = handler.get_jira_project(JIRA_PROJECT_KEY)

        return handler.get_jira_user(JIRA_USER["emailAddress"], jira_project)

    def test_get_sg_user_from_jira_cloud_user(self, mocked_sg):
        """"""
        sg_user = self._test_get_sg_user(
            mocked_sg, JIRA_USER["accountId"], is_jira_cloud=True, jira_user=JIRA_USER
        )
        self.assertEqual(sg_user["id"], self.user["id"])
        self.assertEqual(sg_user["email"], self.user["email"])
        self.assertEqual(sg_user["name"], self.user["name"])

    def test_get_sg_user_from_jira_server_user(self, mocked_sg):
        """"""
        sg_user = self._test_get_sg_user(
            mocked_sg, JIRA_USER["name"], is_jira_cloud=False, jira_user=JIRA_USER
        )
        self.assertEqual(sg_user["id"], self.user["id"])
        self.assertEqual(sg_user["email"], self.user["email"])
        self.assertEqual(sg_user["name"], self.user["name"])

    def test_get_sg_user_without_jira_cloud_user(self, mocked_sg):
        """"""
        sg_user = self._test_get_sg_user(
            mocked_sg, JIRA_USER["accountId"], is_jira_cloud=True
        )
        self.assertEqual(sg_user["id"], self.user["id"])
        self.assertEqual(sg_user["email"], self.user["email"])
        self.assertEqual(sg_user["name"], self.user["name"])

    def test_get_sg_user_without_jira_server_user(self, mocked_sg):
        """"""
        sg_user = self._test_get_sg_user(
            mocked_sg, JIRA_USER["name"], is_jira_cloud=False
        )
        self.assertEqual(sg_user["id"], self.user["id"])
        self.assertEqual(sg_user["email"], self.user["email"])
        self.assertEqual(sg_user["name"], self.user["name"])

    def _test_get_sg_user(self, mocked_sg, user_id, is_jira_cloud=True, jira_user=None):
        """"""

        # Force JIRA cloud or not on the session, which will impact how the
        # webhook data is interpreted.
        patcher = mock.patch(
            "sg_jira.jira_session.JiraSession.is_jira_cloud",
            new_callable=mock.PropertyMock,
            return_value=is_jira_cloud,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        handler = self._get_handler(mocked_sg)

        # add the faked PTR user
        self.add_to_sg_mock_db(handler._shotgun, self.user)

        return handler.get_sg_user(user_id, jira_user)
