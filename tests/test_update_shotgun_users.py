# -*- coding: utf-8 -*-
# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
import os

from shotgun_api3.lib import mockgun

from update_shotgun_users import sync_jira_users_into_shotgun
from sg_jira.jira_session import JiraSession

from mock_jira import JIRA_PROJECT, JIRA_USER, JIRA_USER_2
from test_base import TestBase


class TestUpdateShotgunUsers(TestBase):
    """
    Test hierarchy syncer example.
    """

    def setUp(self):
        # Switch to a schema with needed fields
        self.set_sg_mock_schema(
            os.path.join(os.path.dirname(__file__), "fixtures", "schemas", "sg-jira")
        )
        self._shotgun = mockgun.Shotgun(
            "http://unit_test_mock_sg", "mock_user", "mock_key"
        )
        self.mock_jira_session_bases()

        self.add_to_sg_mock_db(
            self._shotgun,
            [
                {
                    "type": "HumanUser",
                    "id": 1,
                    "login": "ford.prefect.admin",
                    "email": "fprefect@weefree.com",
                    "sg_jira_account_id": None,
                },
                {
                    "type": "HumanUser",
                    "id": 2,
                    "login": "ford.prefect",
                    "email": "fprefect@weefree.com",
                    "sg_jira_account_id": None,
                },
                {
                    "type": "HumanUser",
                    "id": 3,
                    "login": "sync.sync",
                    "email": "syncsync.@foo.com",
                    "sg_jira_account_id": None,
                },
                {
                    "type": "HumanUser",
                    "id": 4,
                    "login": "joe.smith",
                    "email": "joe.smith@foo.com",
                    "sg_jira_account_id": None,
                },
            ],
        )

        self._jira = JiraSession("https://somesite")
        self._jira._is_jira_cloud = True
        self._jira.set_projects([JIRA_PROJECT])

    def test_users_get_synced_properly(self):
        """
        Test syncing links from SG to Jira.
        """
        # Due to the way users are set up in the setUp method, we'll test
        # 1. The first of two users with the same email will be assigned the account id.
        # 2. Each email gets the appropriate accountId
        # 3. Users that do not exist are not matched.
        sync_jira_users_into_shotgun(self._shotgun, self._jira, "UTest")
        self._assert_sg_users_account_ids(JIRA_USER, None, JIRA_USER_2, None)

    def test_transfering_account_id_works(self):
        """
        Test that reassigning an account id to a different user with the same email
        works.
        """
        sync_jira_users_into_shotgun(self._shotgun, self._jira, "UTest")
        # User 1 and 2 have the same email, so we'll transfer the account id to the second
        # user.
        self._shotgun.update("HumanUser", 1, {"sg_jira_account_id": None})
        self._shotgun.update(
            "HumanUser", 2, {"sg_jira_account_id": JIRA_USER["accountId"]}
        )
        # Running the script again shouldn't change anything.
        sync_jira_users_into_shotgun(self._shotgun, self._jira, "UTest")
        self._assert_sg_users_account_ids(None, JIRA_USER, JIRA_USER_2, None)

    def test_new_users_get_assigned(self):
        """
        Test that if some users have already been set that they are untouched but others
        are set.
        """
        # We'll fake a user having already been assigned.
        self._shotgun.update(
            "HumanUser", 2, {"sg_jira_account_id": JIRA_USER["accountId"]}
        )
        sync_jira_users_into_shotgun(self._shotgun, self._jira, "UTest")
        self._assert_sg_users_account_ids(None, JIRA_USER, JIRA_USER_2, None)

    def _assert_sg_users_account_ids(self, *jira_users):
        """
        Ensure each user in Shotgun have the right JIRA accountId.

        :param list(dict) jira_users: List of JIRA user dictionary. The first
            JIRA user is for Shotgun user 1, and so on. If the associated Shotgun
            user has no accountId, then the JIRA user can be None.
        """
        self.assertEqual(len(jira_users), 4)
        self._assert_sg_user_account_id(1, jira_users[0])
        self._assert_sg_user_account_id(2, jira_users[1])
        self._assert_sg_user_account_id(3, jira_users[2])
        self._assert_sg_user_account_id(4, jira_users[3])

    def _assert_sg_user_account_id(self, entity_id, expected_jira_user):
        """
        Ensure that the Shotgun user with a given id is associated with the
        given jira user.

        :param int entity_id: Id of the Shotgun user.
        :param dict expected_jira_user: Expected JIRA user dictionary. Can be None.
        """
        account_id = self._shotgun.find_one(
            "HumanUser", [["id", "is", entity_id]], ["sg_jira_account_id"]
        )["sg_jira_account_id"]
        self.assertEqual(
            account_id, expected_jira_user["accountId"] if expected_jira_user else None
        )
