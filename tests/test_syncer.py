# -*- coding: utf-8 -*-
# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import logging
import mock

from shotgun_api3.lib import mockgun

from test_base import TestBase
from mock_jira import MockedJira
from mock_jira import JIRA_PROJECT_KEY, JIRA_PROJECT, JIRA_USER, JIRA_USER_2
import sg_jira
from sg_jira.constants import SHOTGUN_JIRA_ID_FIELD

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
# Faked SG event meta data
SG_EVENT_META = {
    "attribute_name": "sg_status_list",
    "entity_id": 11793,
    "entity_type": "Task",
    "field_data_type": "status_list",
    "new_value": "wtg",
    "old_value": "fin",
    "type": "attribute_change"
}

JIRA_SUMMARY_CHANGE = {
    "field": "summary",
    "fieldId": "summary",
    "fieldtype": "jira",
    "from": None,
    "fromString": "foo ba",
    "to": None,
    "toString": "foo bar"
}

JIRA_UNASSIGNEE_CHANGE = {
    "from": JIRA_USER["key"],
    "to": None,
    "fromString": JIRA_USER["displayName"],
    "field": "assignee",
    "toString": None,
    "fieldtype": "jira",
    "fieldId": "assignee"
}

JIRA_ASSIGNEE_CHANGE = {
    "from": JIRA_USER_2["key"],
    "to": JIRA_USER["key"],
    "fromString": JIRA_USER_2["displayName"],
    "field": "assignee",
    "toString": JIRA_USER["displayName"],
    "fieldtype": "jira",
    "fieldId": "assignee"
}

JIRA_UNLABEL_CHANGE = {
    "from": None,
    "to": None,
    "fromString": "foo bar",
    "field": "labels",
    "toString": "",
    "fieldtype": "jira",
    "fieldId": "labels"
}

JIRA_LABEL_CHANGE = {
    "from": None,
    "to": None,
    "fromString": "foo",
    "field": "labels",
    "toString": "bar blah",
    "fieldtype": "jira",
    "fieldId": "labels"
}

JIRA_STATUS_CHANGE = {
    "from": 1234,
    "to": 5678,
    "fromString": "Selected for Development",
    "field": "status",
    "toString": "Backlog",
    "fieldtype": "jira",
}

JIRA_STATUS_CHANGE_2 = {
    "from": 5678,
    "to": 1234,
    "fromString": "Backlog",
    "field": "status",
    "toString": "Unknown status for Shotgun",
    "fieldtype": "jira",
    "fieldId": "status"
}


JIRA_ISSUE_FIELDS = {
    "assignee": JIRA_USER,
    "attachment": [],
    "components": [],
    "created": "2018-12-18T06:15:05.626-0500",
    "creator": {
        "accountId": "557058:aecf5cfd-e13d-45a4-8db5-59da3ad254ce",
        "active": True,
        "displayName": "Sync Sync",
        "emailAddress": "syncsync@blah.com",
        "key": "syncsync",
        "name": "syncsync",
        "self": "https://myjira.atlassian.net/rest/api/2/user?accountId=123456%3Aaecf5cfd-e13d-abcdef",
        "timeZone": "America/New_York"
    },
    "customfield_11501": "11794",
    "customfield_11502": "Task",
    "description": "Task (11794)",
    "duedate": None,
    "environment": None,
    "fixVersions": [],
    "issuelinks": [],
    "issuetype": {
        "avatarId": 10318,
        "description": "A task that needs to be done.",
        "iconUrl": "https://myjira.atlassian.net/secure/viewavatar?size=xsmall&avatarId=10318&avatarType=issuetype",
        "id": "10000",
        "name": "Task",
        "self": "https://myjira.atlassian.net/rest/api/2/issuetype/10000",
        "subtask": False
    },
    "labels": [],
    "lastViewed": "2018-12-18T09:44:27.653-0500",
    "priority": {
        "iconUrl": "https://myjira.atlassian.net/images/icons/priorities/medium.svg",
        "id": "3",
        "name": "Medium",
        "self": "https://myjira.atlassian.net/rest/api/2/priority/3"
    },
    "project": JIRA_PROJECT,
    "reporter": {
        "accountId": "557058:aecf5cfd-e13d-45a4-8db5-59da3ad254ce",
        "active": True,
        "displayName": "Shotgun Synch",
        "emailAddress": "stephane.deverly@shotgunsoftware.com",
        "key": "shotgun-synch",
        "name": "shotgun-synch",
        "self": "https://myjira.atlassian.net/rest/api/2/user?accountId=557058%3Aaecf5cfd-e13d-45a4-8db5-59da3ad254ce",
        "timeZone": "America/New_York"
    },
    "resolution": None,
    "resolutiondate": None,
    "security": None,
    "status": {
        "description": "",
        "iconUrl": "https://myjira.atlassian.net/",
        "id": "10204",
        "name": "Backlog",
        "self": "https://myjira.atlassian.net/rest/api/2/status/10204",
        "statusCategory": {
            "colorName": "blue-gray",
            "id": 2,
            "key": "new",
            "name": "New",
            "self": "https://myjira.atlassian.net/rest/api/2/statuscategory/2"
        }
    },
    "subtasks": [],
    "summary": "foo bar",
    "updated": "2018-12-18T09:44:27.572-0500",
    "versions": [],
    "votes": {
        "hasVoted": False,
        "self": "https://myjira.atlassian.net/rest/api/2/issue/ST3-4/votes",
        "votes": 0
    },
    "watches": {
        "isWatching": False,
        "self": "https://myjira.atlassian.net/rest/api/2/issue/ST3-4/watchers",
        "watchCount": 1
    },
    "workratio": -1
}

JIRA_EVENT = {
    "changelog": {
        "id": "123456",
        "items": [JIRA_SUMMARY_CHANGE]
    },
    "issue": {
        "fields": JIRA_ISSUE_FIELDS,
        "id": "16642",
        "key": "ST3-4",
        "self": "https://myjira.atlassian.net/rest/api/2/issue/16642"
    },
    "issue_event_type_name": "issue_updated",
    "timestamp": 1545144267596,
    "user": {
        "accountId": "5b2be739a85c485354681b3b",
        "active": True,
        "displayName": "Marvin Paranoid",
        "emailAddress": "mparanoid@weefree.com",
        "key": "marvin.paranoid",
        "name": "marvin.paranoid",
        "self": "https://myjira.atlassian.net/rest/api/2/user?accountId=5b2be739abcdef",
        "timeZone": "Europe/Paris"
    },
    "webhookEvent": "jira:issue_updated"
}


class ExtMockgun(mockgun.Shotgun):
    """
    Add missing mocked methods to mockgun.Shotgun
    """
    def add_user_agent(*args, **kwargs):
        pass

    def set_session_uuid(*args, **kwargs):
        pass


# Mock Shotgun with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
# Mock Jira with MockedJira, this works only if the code uses jira.client.JIRA
# and does not use `from jira import JIRA` and then `jira_handle = JIRA(...)`
@mock.patch("jira.client.JIRA")
class TestJiraSyncer(TestBase):
    """
    Test syncing from Shotgun to Jira.
    """
    def _get_mocked_sg_handle(self):
        """
        Return a mocked SG handle.
        """
        return ExtMockgun(
            "https://mocked.my.com",
            "Ford Prefect",
            "xxxxxxxxxx",
        )

    def _get_syncer(self, mocked_jira, mocked_sg, name="task_issue"):
        """
        Helper to get a syncer and a bridge with a mocked Shotgun.

        :param mocked_jira: Mocked jira.client.JIRA.
        :param mocked_sg: Mocked shotgun_api3.Shotgun.
        :parma str name: A syncer name.
        """
        mocked_jira.return_value = MockedJira()
        mocked_sg.return_value = self._get_mocked_sg_handle()
        bridge = sg_jira.Bridge.get_bridge(
            os.path.join(self._fixtures_path, "settings.py")
        )
        syncer = bridge.get_syncer(name)
        if syncer:
            syncer._logger.setLevel(logging.WARNING)
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

    def test_bad_syncer(self, mocked_jira, mocked_sg):
        """
        Test we handle problems gracefully and that syncers settings are
        correctly handled.
        """
        # Bad setup should raise an exception
        self.assertRaisesRegexp(
            RuntimeError,
            "Sorry, I'm bad!",
            self._get_syncer,
            mocked_jira,
            mocked_sg,
            "bad_setup"
        )

        bridge = sg_jira.Bridge.get_bridge(
            os.path.join(self._fixtures_path, "settings.py")
        )
        self.assertRaisesRegexp(
            RuntimeError,
            "Sorry, I'm bad!",
            bridge.sync_in_jira,
            "bad_sg_accept",
            "Task",
            123,
            {
                "user": bridge.current_shotgun_user,
                "project": {"type": "Project", "id": 1},
                "meta": SG_EVENT_META
            }
        )
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
    def test_shotgun_event_accept(self, mocked_cur_user, mocked_jira, mocked_sg):
        """
        Test syncer accepts the right Shotgun events.
        """
        mocked_cur_user.return_value = {"type": "ApiUser", "id": 1}
        syncer, bridge = self._get_syncer(mocked_jira, mocked_sg)
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

    def test_jira_event_accept(self, mocked_jira, mocked_sg):
        """
        Test syncer accepts the right Jira events.
        """
        syncer, bridge = self._get_syncer(mocked_jira, mocked_sg)
        # Check an empty event does not cause problems
        self.assertFalse(
            syncer.accept_jira_event(
                "Issue",
                "FAKED-001",
                event={}
            )
        )
        # Check a valid event is accepted
        self.assertTrue(
            syncer.accept_jira_event(
                "Issue",
                "FAKED-001",
                event=JIRA_EVENT
            )
        )

        # Events without a webhookEvent key should be rejected
        event = dict(JIRA_EVENT)
        del event["webhookEvent"]
        self.assertFalse(
            syncer.accept_jira_event(
                "Issue",
                "FAKED-001",
                event=event
            )
        )
        # We support only a couple of webhook events.
        event = dict(JIRA_EVENT)
        event["webhookEvent"] = "this is not valid"
        self.assertFalse(
            syncer.accept_jira_event(
                "Issue",
                "FAKED-001",
                event=event
            )
        )
        # A changelog is needed
        event = dict(JIRA_EVENT)
        del event["changelog"]
        self.assertFalse(
            syncer.accept_jira_event(
                "Issue",
                "FAKED-001",
                event=event
            )
        )
        # Events triggered by the syncer should be ignored
        event = dict(JIRA_EVENT)
        event["user"] = {
            "accountId": "5b2be739a85c485354681b3b",
            "active": True,
            "emailAddress": "foo@blah.com",
            "key": bridge.current_jira_username,
            "name": bridge.current_jira_username,
        }
        self.assertFalse(
            syncer.accept_jira_event(
                "Issue",
                "FAKED-001",
                event=event
            )
        )

    def test_project_match(self, mocked_jira, mocked_sg):
        """
        Test matching a Project between Shotgun and Jira, handling Jira
        create meta data and creating an Issue.
        """
        syncer, bridge = self._get_syncer(mocked_jira, mocked_sg)
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
            ValueError,
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
        bridge.jira.set_projects([JIRA_PROJECT])
        # Faked Jira create meta data with a required field with no default value.
        createmeta = {
            "projects": [
                {"issuetypes": [
                    {"fields": {"faked": {"name": "Faked", "required": True, "hasDefaultValue": False}}}
                ]}
            ]
        }
        # Test missing values in data
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
        # Test valid values in data
        bridge.sync_in_jira(
            "task_issue",
            "Task",
            2,
            {
                "user": {"type": "HumanUser", "id": 1},
                "project": {"type": "Project", "id": 2},
                "meta": SG_EVENT_META
            }
        )

    def test_shotgun_assignee(self, mocked_jira, mocked_sg):
        """
        Test matching Shotgun assignment to Jira.
        """
        syncer, bridge = self._get_syncer(mocked_jira, mocked_sg)
        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECTS)
        self.add_to_sg_mock_db(bridge.shotgun, SG_TASKS)
        self.add_to_sg_mock_db(bridge.shotgun, {
            "status": "act",
            "valid": "valid",
            "type": "HumanUser",
            "name": "Ford Prefect",
            "id": 1,
            "email": JIRA_USER["emailAddress"]
        })
        self.add_to_sg_mock_db(bridge.shotgun, {
            "status": "act",
            "valid": "valid",
            "type": "HumanUser",
            "name": "Sync sync",
            "id": 2,
            "email": JIRA_USER_2["emailAddress"]
        })
        bridge.jira.set_projects([JIRA_PROJECT])
        # Remove the user used when the Issue is created
        bridge.sync_in_jira(
            "task_issue",
            "Task",
            2,
            {
                "user": {"type": "HumanUser", "id": 1},
                "project": {"type": "Project", "id": 2},
                "meta": {
                    "entity_id": 28786,
                    "added": [],
                    "attribute_name": "task_assignees",
                    "entity_type": "Task",
                    "field_data_type": "multi_entity",
                    "removed": [
                        {"status": "act", "valid": "valid", "type": "HumanUser", "id": 1}
                    ],
                    "type": "attribute_change",
                }
            }
        )
        task = bridge.shotgun.find_one(
            "Task",
            [["id", "is", 2]],
            [SHOTGUN_JIRA_ID_FIELD]
        )
        issue = bridge.jira.issue(task[SHOTGUN_JIRA_ID_FIELD])
        self.assertIsNone(issue.fields.assignee)
        # Add an assignee
        bridge.sync_in_jira(
            "task_issue",
            "Task",
            2,
            {
                "user": {"type": "HumanUser", "id": 1},
                "project": {"type": "Project", "id": 2},
                "meta": {
                    "entity_id": 28786,
                    "removed": [],
                    "attribute_name": "task_assignees",
                    "entity_type": "Task",
                    "field_data_type": "multi_entity",
                    "added": [
                        {"status": "act", "valid": "valid", "type": "HumanUser", "id": 1}
                    ],
                    "type": "attribute_change",
                }
            }
        )
        self.assertEqual(issue.fields.assignee.key, JIRA_USER["key"])
        # Replace the current assignee
        bridge.sync_in_jira(
            "task_issue",
            "Task",
            2,
            {
                "user": {"type": "HumanUser", "id": 1},
                "project": {"type": "Project", "id": 2},
                "meta": {
                    "entity_id": 28786,
                    "removed": [
                        {"status": "act", "valid": "valid", "type": "HumanUser", "id": 1}
                    ],
                    "attribute_name": "task_assignees",
                    "entity_type": "Task",
                    "field_data_type": "multi_entity",
                    "added": [
                        {"status": "act", "valid": "valid", "type": "HumanUser", "id": 2}
                    ],
                    "type": "attribute_change",
                }
            }
        )
        self.assertEqual(issue.fields.assignee.key, JIRA_USER_2["key"])
        # Change the Issue assignee
        issue.update(fields={"assignee": JIRA_USER})
        self.assertEqual(issue.fields.assignee.key, JIRA_USER["key"])
        # An update with another assignee shouldn't remove the value
        bridge.sync_in_jira(
            "task_issue",
            "Task",
            2,
            {
                "user": {"type": "HumanUser", "id": 1},
                "project": {"type": "Project", "id": 2},
                "meta": {
                    "entity_id": 28786,
                    "removed": [
                        {"status": "act", "valid": "valid", "type": "HumanUser", "id": 2}
                    ],
                    "attribute_name": "task_assignees",
                    "entity_type": "Task",
                    "field_data_type": "multi_entity",
                    "added": [
                    ],
                    "type": "attribute_change",
                }
            }
        )
        self.assertEqual(issue.fields.assignee.key, JIRA_USER["key"])
        # An update with the assignee should remove the value
        bridge.sync_in_jira(
            "task_issue",
            "Task",
            2,
            {
                "user": {"type": "HumanUser", "id": 1},
                "project": {"type": "Project", "id": 2},
                "meta": {
                    "entity_id": 28786,
                    "removed": [
                        {"status": "act", "valid": "valid", "type": "HumanUser", "id": 2},
                        {"status": "act", "valid": "valid", "type": "HumanUser", "id": 1},
                    ],
                    "attribute_name": "task_assignees",
                    "entity_type": "Task",
                    "field_data_type": "multi_entity",
                    "added": [
                    ],
                    "type": "attribute_change",
                }
            }
        )
        self.assertIsNone(issue.fields.assignee)

    def test_jira_assignment(self, mocked_jira, mocked_sg):
        """
        Test syncing Jira assignment to Shotgun
        """
        syncer, bridge = self._get_syncer(mocked_jira, mocked_sg)

        self.add_to_sg_mock_db(bridge.shotgun, {
            "status": "act",
            "valid": "valid",
            "type": "HumanUser",
            "name": "Ford Prefect",
            "id": 1,
            "email": JIRA_USER["emailAddress"]
        })
        self.add_to_sg_mock_db(bridge.shotgun, {
            "status": "act",
            "valid": "valid",
            "type": "HumanUser",
            "name": "Sync sync",
            "id": 2,
            "email": JIRA_USER_2["emailAddress"]
        })

        self.add_to_sg_mock_db(bridge.shotgun, {
            "status": "act",
            "valid": "valid",
            "type": "HumanUser",
            "name": "Unknown in Jira",
            "id": 3,
            "email": "youdontknow@me.com"
        })

        sg_entity_id = int(JIRA_EVENT["issue"]["fields"]["customfield_11501"])
        sg_entity_type = JIRA_EVENT["issue"]["fields"]["customfield_11502"]

        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECTS)
        self.add_to_sg_mock_db(
            bridge.shotgun, {
                "type": sg_entity_type,
                "id": sg_entity_id,
                "content": "%s (%d)" % (sg_entity_type, sg_entity_id),
                "task_assignees": [{"type": "HumanUser", "id": 1}],
                "project": SG_PROJECTS[0]
            }
        )
        jira_event = dict(JIRA_EVENT)
        jira_event["changelog"] = {
            "id": "123456",
            "items": [JIRA_UNASSIGNEE_CHANGE]
        }
        self.assertTrue(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                jira_event,
            )
        )
        # The matching assignment should have been removed
        self.assertEqual(
            [],
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["task_assignees"]
            )["task_assignees"]
        )
        jira_event["changelog"] = {
            "id": "123456",
            "items": [JIRA_ASSIGNEE_CHANGE]
        }
        self.assertTrue(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                jira_event,
            )
        )
        # The assignment should have been set
        self.assertEqual(
            [{"id": 1, "type": "HumanUser"}],
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["task_assignees"]
            )["task_assignees"]
        )
        bridge.shotgun.update(
            sg_entity_type, sg_entity_id,
            {"task_assignees": [{"type": "HumanUser", "id": 3}]}
        )
        # Assign the Task to a user which is not known in Jira
        self.assertEqual(
            [{"id": 3, "type": "HumanUser"}],
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["task_assignees"]
            )["task_assignees"]
        )
        self.assertTrue(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                jira_event,
            )
        )
        # The unknown user should have been preserved
        self.assertEqual(
            [{"id": 3, "type": "HumanUser"}, {"id": 1, "type": "HumanUser"}],
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["task_assignees"]
            )["task_assignees"]
        )
        # Assign the Task to a user which is not known in Jira
        bridge.shotgun.update(
            sg_entity_type, sg_entity_id,
            {"task_assignees": [{"type": "HumanUser", "id": 2}]}
        )
        self.assertEqual(
            [{"id": 2, "type": "HumanUser"}],
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["task_assignees"]
            )["task_assignees"]
        )
        self.assertTrue(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                jira_event,
            )
        )
        # the known user should have been removed and the new assignee added
        self.assertEqual(
            [{"id": 1, "type": "HumanUser"}],
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["task_assignees"]
            )["task_assignees"]
        )

    def test_jira_labels(self, mocked_jira, mocked_sg):
        """
        Test syncing Jira labels to Shotgun
        """
        syncer, bridge = self._get_syncer(mocked_jira, mocked_sg)
        sg_entity_id = int(JIRA_EVENT["issue"]["fields"]["customfield_11501"])
        sg_entity_type = JIRA_EVENT["issue"]["fields"]["customfield_11502"]

        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECTS)
        self.add_to_sg_mock_db(
            bridge.shotgun, {
                "type": "Tag",
                "id": 1,
                "name": "foo",
            }
        )
        self.add_to_sg_mock_db(
            bridge.shotgun, {
                "type": "Tag",
                "id": 2,
                "name": "bar",
            }
        )
        self.add_to_sg_mock_db(
            bridge.shotgun, {
                "type": "Tag",
                "id": 3,
                "name": "precious",
            }
        )
        self.add_to_sg_mock_db(
            bridge.shotgun, {
                "type": sg_entity_type,
                "id": sg_entity_id,
                "content": "%s (%d)" % (sg_entity_type, sg_entity_id),
                "tags": [{"type": "Tag", "id": 1, "name": "foo"}],
                "project": SG_PROJECTS[0]
            }
        )
        jira_event = dict(JIRA_EVENT)
        jira_event["changelog"] = {
            "id": "123456",
            "items": [JIRA_UNLABEL_CHANGE]
        }
        self.assertTrue(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                jira_event,
            )
        )
        self.assertEqual(
            [],
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["tags"]
            )["tags"]
        )
        jira_event["changelog"] = {
            "id": "123456",
            "items": [JIRA_LABEL_CHANGE]
        }
        self.assertTrue(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                jira_event,
            )
        )
        self.assertEqual(
            [{"id": 2, "type": "Tag"}],
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["tags"]
            )["tags"]
        )
        # Mockgun update and find behave differently than the Shotgun api which
        # includes a "name" key for all linked entities. We use add_to_sg_mock_db
        # to set the value with a "name" key.
        self.add_to_sg_mock_db(
            bridge.shotgun, {
                "type": sg_entity_type,
                "id": sg_entity_id,
                "content": "%s (%d)" % (sg_entity_type, sg_entity_id),
                "tags": [{"type": "Tag", "id": 3, "name": "precious"}],
                "project": SG_PROJECTS[0]
            }
        )

        self.assertEqual(
            [{"id": 3, "type": "Tag", "name": "precious"}],
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["tags"]
            )["tags"]
        )
        self.assertTrue(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                jira_event,
            )
        )
        # Existing tag should have been preserved, the known one added.
        self.assertEqual(
            [{"id": 3, "type": "Tag"}, {"id": 2, "type": "Tag"}],
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["tags"]
            )["tags"]
        )

    def test_jira_status(self, mocked_jira, mocked_sg):
        """
        Test syncing Jira status to Shotgun
        """
        syncer, bridge = self._get_syncer(mocked_jira, mocked_sg)
        sg_entity_id = int(JIRA_EVENT["issue"]["fields"]["customfield_11501"])
        sg_entity_type = JIRA_EVENT["issue"]["fields"]["customfield_11502"]

        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECTS)
        self.add_to_sg_mock_db(
            bridge.shotgun, {
                "type": sg_entity_type,
                "id": sg_entity_id,
                "content": "%s (%d)" % (sg_entity_type, sg_entity_id),
                "project": SG_PROJECTS[0]
            }
        )
        bridge.shotgun.update(
            sg_entity_type, sg_entity_id,
            {"sg_status_list": "rdy"}
        )
        self.assertEqual(
            "rdy",
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["sg_status_list"]
            )["sg_status_list"]
        )
        jira_event = dict(JIRA_EVENT)
        jira_event["changelog"] = {
            "id": "123456",
            "items": [JIRA_STATUS_CHANGE]
        }
        self.assertTrue(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                jira_event,
            )
        )
        self.assertEqual(
            "hld",
            bridge.shotgun.find_one(
                sg_entity_type,
                [["id", "is", sg_entity_id]],
                ["sg_status_list"]
            )["sg_status_list"]
        )
        jira_event["changelog"] = {
            "id": "123456",
            "items": [JIRA_STATUS_CHANGE_2]
        }
        # Udpate with a status unknown in Shotgun
        self.assertFalse(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                jira_event,
            )
        )

    def test_jira_2_shotgun(self, mocked_jira, mocked_sg):
        """
        Test syncing from Jira to Shotgun
        """
        syncer, bridge = self._get_syncer(mocked_jira, mocked_sg)
        # Syncing without the target entities shouldn't cause problems
        sg_entity_id = int(JIRA_EVENT["issue"]["fields"]["customfield_11501"])
        sg_entity_type = JIRA_EVENT["issue"]["fields"]["customfield_11502"]
        self.assertEqual(
            [],
            bridge.shotgun.find(sg_entity_type, [["id", "is", sg_entity_id]])
        )
        self.assertFalse(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                JIRA_EVENT,
            )
        )
        # No new entity should be created
        self.assertEqual(
            [],
            bridge.shotgun.find(sg_entity_type, [["id", "is", sg_entity_id]])
        )
        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECTS)
        self.add_to_sg_mock_db(
            bridge.shotgun, {
                "type": sg_entity_type,
                "id": sg_entity_id,
                "content": "%s (%d)" % (sg_entity_type, sg_entity_id),
                "task_assignees": [],
                "project": SG_PROJECTS[0]
            }
        )
        self.assertTrue(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                JIRA_EVENT,
            )
        )

    def test_unicode(self, mocked_jira, mocked_sg):
        """
        Test unicode values are correclty handled.
        """
        unicode_string = u"No Sync unicode_îéö_😀"
        encoded_string = unicode_string.encode("utf-8")
        syncer, bridge = self._get_syncer(mocked_jira, mocked_sg)
        # Faked Jira project
        bridge.jira.set_projects([JIRA_PROJECT])
        # Values we get back from Shotgun are never unicode
        sg_project = {"id": 2, "name": encoded_string, "type": "Project", SHOTGUN_JIRA_ID_FIELD: JIRA_PROJECT_KEY}
        self.add_to_sg_mock_db(
            bridge.shotgun,
            sg_project,
        )
        sg_user = {
            "status": "act",
            "valid": "valid",
            "type": "HumanUser",
            "name": "Ford Prefect %s" % encoded_string,
            "id": 1,
            "email": JIRA_USER["emailAddress"]
        }
        self.add_to_sg_mock_db(
            bridge.shotgun,
            [sg_project, sg_user],
        )
        sg_entity_id = int(JIRA_EVENT["issue"]["fields"]["customfield_11501"])
        sg_entity_type = JIRA_EVENT["issue"]["fields"]["customfield_11502"]
        self.assertEqual(
            [],
            bridge.shotgun.find(sg_entity_type, [["id", "is", sg_entity_id]])
        )
        sg_task = {
            "type": sg_entity_type,
            "id": sg_entity_id,
            "content": "%s %s (%d)" % (
                sg_entity_type,
                encoded_string,
                sg_entity_id
            ),
            "task_assignees": [sg_user],
            "project": sg_project,
        }
        self.add_to_sg_mock_db(
            bridge.shotgun, sg_task
        )
        bridge.sync_in_jira(
            "task_issue",
            sg_entity_type,
            sg_entity_id,
            {
                "user": sg_user,
                "project": sg_project,
                "meta": {
                    "type": "attribute_change",
                    "entity_id": sg_entity_id,
                    "attribute_name": "content",
                    "entity_type": sg_entity_type,
                    "field_data_type": "text",
                    "new_value": encoded_string,
                    "old_value": "",
                }
            }
        )
        self.assertTrue(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                JIRA_EVENT,
            )
        )
        jira_event = dict(JIRA_EVENT)
        jira_event["changelog"] = {
            "id": "123456",
            "items": [{
                "from": JIRA_USER_2["key"],
                "to": JIRA_USER["key"],
                "fromString": JIRA_USER_2["displayName"],
                "field": "assignee",
                "toString": sg_user["name"].decode("utf-8"),
                "fieldtype": "jira",
                "fieldId": "assignee"
            }, {
                "field": "summary",
                "fieldId": "summary",
                "fieldtype": "jira",
                "from": None,
                "fromString": "foo ba",
                "to": None,
                "toString": "foo bar %s" % unicode_string
            }]
        }

        self.assertTrue(
            bridge.sync_in_shotgun(
                "task_issue",
                "Issue",
                "FAKED-01",
                jira_event,
            )
        )
        # Retrieve the updated Task and check it
        updated_task = bridge.shotgun.find_one(
            sg_task["type"],
            [["id", "is", sg_task["id"]]],
            fields=sg_task.keys()
        )
        for k, v in updated_task.iteritems():
            # All keys should be unicode
            self.assertTrue(isinstance(k, unicode))
            # We shouldn't have any string value, just unicode
            self.assertFalse(isinstance(v, str))

    def test_shotgun_note(self, mocked_jira, mocked_sg):
        """
        Test syncing a Note from SG to Jira.
        """
        syncer, bridge = self._get_syncer(mocked_jira, mocked_sg)
        # Faked Jira project
        bridge.jira.set_projects([JIRA_PROJECT])
        issue = bridge.jira.create_issue({})
        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECTS)
        synced_task = {
            "type": "Task",
            "id": 3,
            "content": "Task One/2",
            "task_assignees": [],
            "project": SG_PROJECTS[1],
            SHOTGUN_JIRA_ID_FIELD: issue.key
        }
        self.add_to_sg_mock_db(bridge.shotgun, SG_TASKS + [synced_task])

        self.add_to_sg_mock_db(bridge.shotgun, {
            "type": "Note",
            "subject": "This is a note",
            "id": 1,
            "content": "This is the note's content",
            "user": None,
            "tasks": SG_TASKS,
        })
        bridge.jira.set_projects([JIRA_PROJECT])
        # Notes linked to not synced Tasks shouldn't trigger anything
        bridge.sync_in_jira(
            "task_issue",
            "Note",
            1,
            {
                "user": {"type": "HumanUser", "id": 1},
                "project": {"type": "Project", "id": 2},
                "meta": {
                    "entity_id": 1,
                    "added": [],
                    "attribute_name": "tasks",
                    "entity_type": "Note",
                    "field_data_type": "multi_entity",
                    "removed": [
                        SG_TASKS[0]
                    ],
                    "type": "attribute_change",
                }
            }
        )
        updated_note = bridge.shotgun.find_one(
            "Note",
            [["id", "is", 1]],
            [SHOTGUN_JIRA_ID_FIELD],
        )
        self.assertIsNone(updated_note[SHOTGUN_JIRA_ID_FIELD])

        # Adding a synced Tasks should create a comment and the comment key
        bridge.sync_in_jira(
            "task_issue",
            "Note",
            1,
            {
                "user": {"type": "HumanUser", "id": 1},
                "project": {"type": "Project", "id": 2},
                "meta": {
                    "entity_id": 1,
                    "added": [synced_task],
                    "attribute_name": "tasks",
                    "entity_type": "Note",
                    "field_data_type": "multi_entity",
                    "removed": [
                        SG_TASKS[0]
                    ],
                    "type": "attribute_change",
                }
            }
        )
        updated_note = bridge.shotgun.find_one(
            "Note",
            [["id", "is", 1]],
            [SHOTGUN_JIRA_ID_FIELD],
        )
        self.assertEqual(updated_note[SHOTGUN_JIRA_ID_FIELD], "%s/1" % issue.key)

        # Removing a synced Tasks should delete the comment and unset the comment key
        bridge.sync_in_jira(
            "task_issue",
            "Note",
            1,
            {
                "user": {"type": "HumanUser", "id": 1},
                "project": {"type": "Project", "id": 2},
                "meta": {
                    "entity_id": 1,
                    "added": SG_TASKS,
                    "attribute_name": "tasks",
                    "entity_type": "Note",
                    "field_data_type": "multi_entity",
                    "removed": [
                        synced_task
                    ],
                    "type": "attribute_change",
                }
            }
        )
        updated_note = bridge.shotgun.find_one(
            "Note",
            [["id", "is", 1]],
            [SHOTGUN_JIRA_ID_FIELD],
        )
        self.assertIsNone(updated_note[SHOTGUN_JIRA_ID_FIELD])
