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

    def _get_syncer(self, mocked, name="task_issue"):
        self.set_sg_mock_schema(os.path.join(
            os.path.dirname(__file__),
            "fixtures", "schemas", "sg-jira",
        ))
        mocked.return_value = mockgun.Shotgun(
            "https://mocked.my.com",
            "Ford Escort",
            "xxxxxxxxxx",
        )
        bridge = sg_jira.Bridge.get_bridge(
            os.path.join(self._fixtures_path, "settings.py")
        )
        syncer = bridge.get_syncer(name)
        return syncer, bridge

    def test_project_match(self, mocked):
        syncer, _ = self._get_syncer(mocked)
        jira_projects = syncer._bridge._jira.projects()

    def test_bad_syncer(self, mocked):
        """
        Test we handle problems gracefully.
        """
        # The syncer should be disabled because of its bad setup call.
        syncer, bridge = self._get_syncer(mocked, "bad_setup")
        self.assertIsNone(syncer)
        # It shoudl be registered in loaded syncers
        self.assertTrue("bad_setup" in bridge._syncers)

    @mock.patch(
        "sg_jira.Bridge.current_shotgun_user",
        new_callable=mock.PropertyMock
    )
    def test_event_accept(self, mocked_cur_user, mocked):
        """
        Test syncer accepts the right Shotgun events.
        """
        mocked_cur_user.return_value = {"type": "ApiUser", "id": 1}
        syncer, _ = self._get_syncer(mocked)
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
                    "user": syncer._bridge.current_shotgun_user,
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
