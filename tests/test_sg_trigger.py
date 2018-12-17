# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import logging
import datetime
import requests
import mock

from shotgun_api3.lib import mockgun

from test_base import TestBase
import sg_jira_event_trigger

logger = logging.getLogger(__name__)


# Some constants which can be used across tests
PROJECT = {"id": 1, "name": "Bunny", "type": "Project"}
EVENT = {
    "attribute_name": "sg_status_list",
    "created_at": datetime.datetime(2018, 11, 28, 15, 43, 7),
    "entity": {"id": 11793, "name": "Art", "type": "Task"},
    "event_type": "Shotgun_Task_Change",
    "id": 4044184,
    "meta": {
        "attribute_name": "sg_status_list",
        "entity_id": 11793,
        "entity_type": "Task",
        "field_data_type": "status_list",
        "new_value": "wtg",
        "old_value": "fin",
        "type": "attribute_change"
    },
    "project": PROJECT,
    "session_uuid": "e8b61250-f31b-11e8-bb75-0242ac110004",
    "type": "EventLogEntry",
    "user": {
        "id": 42,
        "name": "Ford Escort",
        "type": "HumanUser"
    }
}


def mocked_requests_post(*args, **kwargs):
    """
    Mock requests.post made the trigger and return a Response with the url
    and the payload.
    """
    response = requests.Response()
    response.url = args[0]
    response._contents = kwargs
    return response


class TestSGTrigger(TestBase):
    """
    Tests related to the Shotgun Event trigger.
    """
    def setUp(self):
        logging.basicConfig(format="%(levelname)s:%(name)s:%(message)s")

    def test_project_sync_url_base_schema(self):
        """
        Check nothing bad happens if a Project can't be found or if some
        needed fields are missing in the schema
        """
        self.set_sg_mock_schema(os.path.join(
            os.path.dirname(__file__),
            "fixtures", "schemas", "base",
        ))
        shotgun = mockgun.Shotgun(
            "http://unit_test_mock_sg",
            "mock_user", "mock_key"
        )
        # Check nothing bad happens if a Project can't be found or if some
        # needed fields are missing in the schema
        routing = {}
        sg_jira_event_trigger.process_event(
            shotgun,
            logger,
            EVENT,
            routing
        )
        # Add missing project
        self.add_to_sg_mock_db(shotgun, PROJECT)
        sg_jira_event_trigger.process_event(
            shotgun,
            logger,
            EVENT,
            routing
        )
        self.assertTrue(PROJECT["id"] in routing)

    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_project_sync_url(self, mocked):
        """
        Test retrieving the dispatch url for a Project.
        """
        routing = {}
        # Switch to a schema with needed fields
        self.set_sg_mock_schema(os.path.join(
            os.path.dirname(__file__),
            "fixtures", "schemas", "sg-jira",
        ))
        shotgun = mockgun.Shotgun(
            "http://unit_test_mock_sg",
            "mock_user", "mock_key"
        )
        self.add_to_sg_mock_db(shotgun, PROJECT)
        sg_jira_event_trigger.process_event(
            shotgun,
            logger,
            EVENT,
            routing
        )
        self.assertTrue(PROJECT["id"] in routing)
        self.assertIsNone(routing[PROJECT["id"]])
        routing = {}
        url = "http://localhost/default/sg2jira"
        shotgun.update(
            PROJECT["type"],
            PROJECT["id"],
            data={
                "sg_jira_sync_url": {
                    "content_type": "string",
                    "link_type": "web",
                    "name": "test",
                    "url": "http://localhost/default/sg2jira"
                }
            }
        )
        sg_jira_event_trigger.process_event(
            shotgun,
            logger,
            EVENT,
            routing
        )
        self.assertTrue(PROJECT["id"] in routing)
        self.assertTrue(routing[PROJECT["id"]].startswith(url))
        mocked.assert_called_once()
        self.assertTrue(mocked.call_args[0][0].startswith(url))
        # Check the trigger clears its routing cache if the sync url is changed
        project_event = {
            "event_type": "Shotgun_Project_Change",
            "entity": PROJECT,
            "project": None,
            "attribute_name": "sg_jira_sync_url",
            "meta": {
                "type": "attribute_change",
                "attribute_name": "sg_jira_sync_url",
                "entity_type": PROJECT["type"],
                "entity_id": PROJECT["id"],
                "field_data_type": "url",
                "old_value": None,
                "new_value": {
                    "attachment_id": 1416,
                    "attachment_type": "http_url",
                    "display_name": "Jira Sync",
                    "icon_url": "/images/filetypes/filetype_icon_misc.png",
                    "icon_class": "icon_web",
                    "url": "http://localhost/default/sg2jira",
                    "attachment_uuid": "abcdefg"
                }
            }
        }
        sg_jira_event_trigger.process_event(
            shotgun,
            logger,
            project_event,
            routing
        )
        self.assertFalse(PROJECT["id"] in routing)
        # Processing the Task event should cache the routing again
        sg_jira_event_trigger.process_event(
            shotgun,
            logger,
            EVENT,
            routing
        )
        self.assertTrue(PROJECT["id"] in routing)
        self.assertTrue(routing[PROJECT["id"]].startswith(url))
        mocked.assert_called()
        self.assertTrue(mocked.call_args[0][0].startswith(url))
