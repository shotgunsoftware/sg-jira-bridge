# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import logging
import unittest2 as unittest
import mock

from shotgun_api3.lib import mockgun

from test_base import TestBase

import sg_jira
from sg_jira.constants import SHOTGUN_JIRA_ID_FIELD
from jira.resources import Project as JiraProject

# A faked Jira Project key
JIRA_PROJECT_KEY = "UTest"
# A list of Shotgun Projects
SG_PROJECTS = [
    {"id": 1, "name": "No Sync", "type": "Project"},
    {"id": 2, "name": "Sync", "type": "Project", SHOTGUN_JIRA_ID_FIELD: JIRA_PROJECT_KEY}
]

# A list of Shotgun Tasks
SG_TASKS = [
    {
        "type": "Task",
        "id": 1,
        "content": "Task One/1",
        "task_assignees": [],
        "project": SG_PROJECTS[0]
    },
    {
        "type": "Task",
        "id": 2,
        "content": "Task One/2",
        "task_assignees": [],
        "project": SG_PROJECTS[1]
    },
]
# Faked event meta data
SG_EVENT_META = {
    "attribute_name": "sg_status_list",
    "entity_id": 11793,
    "entity_type": "Task",
    "field_data_type": "status_list",
    "new_value": "wtg",
    "old_value": "fin",
    "type": "attribute_change"
}


# We need a valid connection to Jira, Shotgun is mocked
@unittest.skipUnless(
    os.environ.get("SG_JIRA_JIRA_SITE")
    and os.environ.get("SG_JIRA_JIRA_USER")
    and os.environ.get("SG_JIRA_JIRA_USER_SECRET"),
    "Requires SG_JIRA_JIRA_SITE, SG_JIRA_JIRA_USER, SG_JIRA_JIRA_USER_SECRET env vars."
)
# Mock Shotgun with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
class TestJiraSyncer(TestBase):
    """
    Test syncing from Shotgun to Jira.
    """
    def _get_mocked_sg_handle(self):
        """
        Return a mocked SG handle.
        """
        return mockgun.Shotgun(
            "https://mocked.my.com",
            "Ford Escort",
            "xxxxxxxxxx",
        )

    def _get_syncer(self, mocked, name="task_issue"):
        """
        Helper to get a syncer and a bridge with a mocked Shotgun.

        :param mocked: Mocked shotgun_api3.Shotgun.
        :parma str name: A syncer name.
        """
        mocked.return_value = self._get_mocked_sg_handle()
        bridge = sg_jira.Bridge.get_bridge(
            os.path.join(self._fixtures_path, "settings.py")
        )
        syncer = bridge.get_syncer(name)
        return syncer, bridge

    def setUp(self):
        """
        Test setup.
        """
        super(TestJiraSyncer, self).setUp()
        self.set_sg_mock_schema(os.path.join(
            os.path.dirname(__file__),
            "fixtures", "schemas", "sg-jira",
        ))

    def test_bad_syncer(self, mocked):
        """
        Test we handle problems gracefully and that syncers settings are
        correctly handled.
        """
        # The syncer should be disabled because of its bad setup call.
        syncer, bridge = self._get_syncer(mocked, "bad_setup")
        self.assertIsNone(syncer)
        # It should be registered in loaded syncers
        self.assertTrue("bad_setup" in bridge._syncers)
        #
        self.assertRaisesRegexp(
            RuntimeError,
            "Sorry, I'm bad!",
            bridge.sync_in_jira,
            "bad_sg_sync",
            "Task",
            123,
            {
                "user": bridge.current_shotgun_user,
                "project": {"type": "Project", "id": 1},
                "meta": SG_EVENT_META
            }
        )

    @mock.patch(
        "sg_jira.Bridge.current_shotgun_user",
        new_callable=mock.PropertyMock
    )
    def test_event_accept(self, mocked_cur_user, mocked):
        """
        Test syncer accepts the right Shotgun events.
        """
        mocked_cur_user.return_value = {"type": "ApiUser", "id": 1}
        syncer, bridge = self._get_syncer(mocked)
        syncer.logger.setLevel(logging.DEBUG)
        # Empty events should be rejected
        self.assertFalse(
            syncer.accept_shotgun_event(
                "Task",
                123,
                event={}
            )
        )
        # Events without a Project should be rejected
        self.assertFalse(
            syncer.accept_shotgun_event(
                "Task",
                123,
                event={
                    "meta": SG_EVENT_META
                }
            )
        )
        # Events with a Project and a different user than the one used by
        # the bridge for Shotgun connection should be accepted
        self.assertTrue(
            syncer.accept_shotgun_event(
                "Task",
                123,
                event={
                    "project": {"type": "Project", "id": 1},
                    "user": {"type": "HumanUser", "id": 1},
                    "meta": SG_EVENT_META
                }
            )
        )
        # Events generated by ourself should be rejected
        self.assertFalse(
            syncer.accept_shotgun_event(
                "Task",
                123,
                event={
                    "user": bridge.current_shotgun_user,
                    "project": {"type": "Project", "id": 1},
                    "meta": SG_EVENT_META
                }
            )
        )
        # Task <-> Issue syncer should only accept Tasks
        self.assertFalse(
            syncer.accept_shotgun_event(
                "Ticket",
                123,
                event={
                    "user": {"type": "HumanUser", "id": 1},
                    "project": {"type": "Project", "id": 1},
                    "meta": SG_EVENT_META
                }
            )
        )

    def test_project_match(self, mocked):
        """
        """
        syncer, bridge = self._get_syncer(mocked)
        syncer.logger.setLevel(logging.DEBUG)
        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECTS)
        self.add_to_sg_mock_db(bridge.shotgun, SG_TASKS)

        ret = bridge.sync_in_jira(
            "task_issue",
            "Task",
            1,
            event={
                "user": {"type": "HumanUser", "id": 1},
                "project": {"type": "Project", "id": 1},
                "meta": SG_EVENT_META
            }
        )
        self.assertFalse(ret)
        # Just make sure our faked Project does not really exist.
        self.assertFalse(syncer.get_jira_project(JIRA_PROJECT_KEY))
        # An error should be raised If the Project is linked to a bad Jira
        # Project
        self.assertRaisesRegexp(
            RuntimeError,
            "Unable to retrieve a Jira Project",
            bridge.sync_in_jira,
            "task_issue",
            "Task",
            2,
            {
                "user": {"type": "HumanUser", "id": 1},
                "project": {"type": "Project", "id": 2},
                "meta": SG_EVENT_META
            }
        )
        # Faked Jira project
        jira_project = JiraProject(
            None,
            None,
            raw={
                "name": "Tasks unit test",
                "self": "https://mocked.faked.com/rest/api/2/project/10400",
                "projectTypeKey": "software",
                "simplified": False,
                "key": JIRA_PROJECT_KEY,
                "isPrivate": False,
                "id": "12345",
                "expand": "description,lead,issueTypes,url,projectKeys"
            }
        )
        # Faked Jira create meta data with a required field with no default value.
        createmeta = {"projects": [
            {"issuetypes": [
                {"fields": {"faked": {"name": "Faked", "required": True, "hasDefaultValue": False}}}
            ]}
        ]}
        with mock.patch.object(syncer, "get_jira_project", return_value=jira_project) as m_project: # noqa
            with mock.patch.object(syncer.jira, "createmeta", return_value=createmeta) as m_cmeta:  # noqa
                # This should fail because of missing data for the required "Faked" field
                self.assertRaisesRegexp(
                    ValueError,
                    r"The following data is missing in order to create a Jira Task Issue: \['Faked'\]",
                    bridge.sync_in_jira,
                    "task_issue",
                    "Task",
                    2,
                    {
                        "user": {"type": "HumanUser", "id": 1},
                        "project": {"type": "Project", "id": 2},
                        "meta": SG_EVENT_META
                    }
                )

