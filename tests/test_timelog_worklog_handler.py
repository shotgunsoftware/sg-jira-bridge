# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import datetime
import json

import mock
from mock_jira import JIRA_PROJECT, JIRA_USER_2
from mock_shotgun import (
    SG_PROJECT,
    SG_RETIRED_TIMELOG,
    SG_TASK,
    SG_TIMELOG,
    SG_USER,
    SG_USER_2,
)
from test_sync_base import TestSyncBase

from sg_jira.constants import SHOTGUN_JIRA_ID_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD

JIRA_SHOTGUN_TIMELOG_FIELD = "Shotgun TimeLogs"
JIRA_SHOTGUN_ID_FIELD = "Shotgun ID"


# Mock Flow Production Tracking with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
class TestTimelogWorklogHandler(TestSyncBase):
    """Test class for TimelogWorklogHandler class."""

    def setUp(self):
        """Test setup."""

        super(TestTimelogWorklogHandler, self).setUp()

    def test_sg_to_jira_add_timelog(self, mocked_sg):
        """Test adding a new timelog in Flow Production Tracking"""

        syncer, bridge = self._get_syncer(mocked_sg, name="timelog")
        jira_field_id = bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_TIMELOG_FIELD)

        # mock the Jira data
        bridge.jira.set_projects([JIRA_PROJECT])
        issue = bridge.jira.create_issue({jira_field_id: ""})

        # mock the PTR data
        sg_task = SG_TASK.copy()
        sg_task[SHOTGUN_JIRA_ID_FIELD] = issue.key
        sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True

        sg_timelog = SG_TIMELOG.copy()
        sg_timelog["entity"] = sg_task

        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECT)
        self.add_to_sg_mock_db(bridge.shotgun, sg_task)
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog)

        # sync the timelog to Jira
        self.assertTrue(
            bridge.sync_in_jira(
                "timelog",
                "TimeLog",
                sg_timelog["id"],
                {
                    "user": {"type": "HumanUser", "id": SG_USER["id"]},
                    "project": {"type": "Project", "id": SG_PROJECT["id"]},
                    "meta": {
                        "type": "attribute_change",
                        "attribute_name": "entity",
                        "entity_type": "TimeLog",
                        "entity_id": sg_timelog["id"],
                        "field_data_type": "entity",
                        "old_value": None,
                        "new_value": sg_task,
                    },
                },
            )
        )

        # the FPT timelog should have been updated with the Jira key
        updated_timelog = bridge.shotgun.find_one(
            "TimeLog", [["id", "is", SG_TIMELOG["id"]]], [SHOTGUN_JIRA_ID_FIELD]
        )
        self.assertIsNotNone(updated_timelog[SHOTGUN_JIRA_ID_FIELD])

        # check that the timelog assignee was correctly stored
        jira_worklog_key = updated_timelog[SHOTGUN_JIRA_ID_FIELD].split("/")[1]
        timelog_data = json.loads(issue.get_field(jira_field_id))
        self.assertEqual(timelog_data[jira_worklog_key]["user"]["id"], SG_USER["id"])

    def test_sg_to_jira_add_timelog_task_non_synced(self, mocked_sg):
        """Test adding a new timelog in Flow Production Tracking to a Task which is not flagged as synced"""

        syncer, bridge = self._get_syncer(mocked_sg, name="timelog")

        # mock the PTR data
        sg_timelog = SG_TIMELOG.copy()
        sg_timelog["entity"] = SG_TASK

        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECT)
        self.add_to_sg_mock_db(bridge.shotgun, SG_TASK)
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog)

        # sync the timelog to Jira
        self.assertFalse(
            bridge.sync_in_jira(
                "timelog",
                "TimeLog",
                sg_timelog["id"],
                {
                    "user": {"type": "HumanUser", "id": SG_USER["id"]},
                    "project": {"type": "Project", "id": SG_PROJECT["id"]},
                    "meta": {
                        "type": "attribute_change",
                        "attribute_name": "entity",
                        "entity_type": "TimeLog",
                        "entity_id": sg_timelog["id"],
                        "field_data_type": "entity",
                        "old_value": None,
                        "new_value": SG_TASK,
                    },
                },
            )
        )

    def test_sg_to_jira_update_timelog(self, mocked_sg):
        """Test updating an existing timelog in Flow Production Tracking"""

        syncer, bridge = self._get_syncer(mocked_sg, name="timelog")
        jira_field_id = bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_TIMELOG_FIELD)

        # mock the Jira data
        bridge.jira.set_projects([JIRA_PROJECT])
        issue = bridge.jira.create_issue({jira_field_id: ""})
        worklog = bridge.jira.add_worklog(
            issue,
            comment="Fake comment",
            timeSpentSeconds=0,
            started="2023-03-15T01:00:00.000+0100",
        )

        # mock the PTR data
        sg_task = SG_TASK.copy()
        sg_task[SHOTGUN_JIRA_ID_FIELD] = issue.key
        sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True

        sg_timelog = SG_TIMELOG.copy()
        sg_timelog["entity"] = sg_task
        sg_timelog[SHOTGUN_JIRA_ID_FIELD] = f"{issue.key}/{worklog.id}"

        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECT)
        self.add_to_sg_mock_db(bridge.shotgun, sg_task)
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog)

        # update the FPT TimeLog description
        self.assertTrue(
            bridge.sync_in_jira(
                "timelog",
                "TimeLog",
                sg_timelog["id"],
                {
                    "user": {"type": "HumanUser", "id": SG_USER["id"]},
                    "project": {"type": "Project", "id": SG_PROJECT["id"]},
                    "meta": {
                        "type": "attribute_change",
                        "attribute_name": "description",
                        "entity_type": "TimeLog",
                        "entity_id": sg_timelog["id"],
                        "field_data_type": "entity",
                        "old_value": "Fake comment",
                        "new_value": SG_TIMELOG["description"],
                    },
                },
            )
        )

        # update the FPT TimeLog duration
        self.assertTrue(
            bridge.sync_in_jira(
                "timelog",
                "TimeLog",
                sg_timelog["id"],
                {
                    "user": {"type": "HumanUser", "id": SG_USER["id"]},
                    "project": {"type": "Project", "id": SG_PROJECT["id"]},
                    "meta": {
                        "type": "attribute_change",
                        "attribute_name": "description",
                        "entity_type": "TimeLog",
                        "entity_id": sg_timelog["id"],
                        "field_data_type": "entity",
                        "old_value": 0,
                        "new_value": SG_TIMELOG["duration"],
                    },
                },
            )
        )

        # update the FPT TimeLog start date
        self.assertTrue(
            bridge.sync_in_jira(
                "timelog",
                "TimeLog",
                sg_timelog["id"],
                {
                    "user": {"type": "HumanUser", "id": SG_USER["id"]},
                    "project": {"type": "Project", "id": SG_PROJECT["id"]},
                    "meta": {
                        "type": "attribute_change",
                        "attribute_name": "date",
                        "entity_type": "TimeLog",
                        "entity_id": sg_timelog["id"],
                        "field_data_type": "entity",
                        "old_value": "2023-03-15",
                        "new_value": SG_TIMELOG["date"],
                    },
                },
            )
        )

        # update the FPT TimeLog assignee
        self.assertTrue(
            bridge.sync_in_jira(
                "timelog",
                "TimeLog",
                sg_timelog["id"],
                {
                    "user": {"type": "HumanUser", "id": SG_USER["id"]},
                    "project": {"type": "Project", "id": SG_PROJECT["id"]},
                    "meta": {
                        "type": "attribute_change",
                        "attribute_name": "user",
                        "entity_type": "TimeLog",
                        "entity_id": sg_timelog["id"],
                        "field_data_type": "entity",
                        "old_value": {
                            "name": "Fake Name",
                            "type": "HumanUser",
                            "id": 2,
                        },
                        "new_value": {
                            "name": SG_USER["name"],
                            "type": SG_USER["type"],
                            "id": SG_USER["id"],
                        },
                    },
                },
            )
        )

        updated_worklog = bridge.jira.worklog(issue.key, worklog.id)
        self.assertEqual(updated_worklog.comment, SG_TIMELOG["description"])
        self.assertEqual(updated_worklog.timeSpentSeconds, SG_TIMELOG["duration"] * 60)
        self.assertEqual(
            updated_worklog.started,
            datetime.datetime.strptime(SG_TIMELOG["date"], "%Y-%m-%d").strftime(
                "%Y-%m-%dT%H:%M:%S.000+0000"
            ),
        )
        timelog_data = json.loads(issue.get_field(jira_field_id))
        self.assertEqual(
            timelog_data[worklog.id]["user"]["id"], SG_TIMELOG["user"]["id"]
        )

    def test_sg_to_jira_delete_timelog_flag_enabled(self, mocked_sg):
        """Test deleting a timelog in Flow Production Tracking when the delete flag is enabled"""

        syncer, bridge = self._get_syncer(mocked_sg, name="timelog")

        jira_field_id = bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_TIMELOG_FIELD)

        # mock the Jira data
        bridge.jira.set_projects([JIRA_PROJECT])
        issue = bridge.jira.create_issue({jira_field_id: ""})
        worklog_1 = bridge.jira.add_worklog(
            issue,
            comment=SG_TIMELOG["description"],
            timeSpentSeconds=SG_TIMELOG["duration"] * 60,
            started=datetime.datetime.strptime(SG_TIMELOG["date"], "%Y-%m-%d").strftime(
                "%Y-%m-%dT%H:%M:%S.000+0000"
            ),
        )
        worklog_2 = bridge.jira.add_worklog(
            issue,
            comment=SG_RETIRED_TIMELOG["description"],
            timeSpentSeconds=SG_RETIRED_TIMELOG["duration"] * 60,
            started=datetime.datetime.strptime(
                SG_RETIRED_TIMELOG["date"], "%Y-%m-%d"
            ).strftime("%Y-%m-%dT%H:%M:%S.000+0000"),
        )
        timelog_data = {
            worklog_1.id: {"user": SG_TIMELOG["user"]},
            worklog_2.id: {"user": SG_RETIRED_TIMELOG["user"]},
        }
        issue.update(fields={jira_field_id: json.dumps(timelog_data)})

        # mock the PTR data
        sg_task = SG_TASK.copy()
        sg_task[SHOTGUN_JIRA_ID_FIELD] = issue.key
        sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True

        sg_retired_timelog = SG_RETIRED_TIMELOG.copy()
        sg_retired_timelog["entity"] = sg_task
        sg_retired_timelog[SHOTGUN_JIRA_ID_FIELD] = f"{issue.key}/{worklog_2.id}"

        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECT)
        self.add_to_sg_mock_db(bridge.shotgun, sg_task)
        self.add_to_sg_mock_db(bridge.shotgun, sg_retired_timelog)

        self.assertTrue(
            bridge.sync_in_jira(
                "timelog",
                "TimeLog",
                SG_RETIRED_TIMELOG["id"],
                {
                    "user": {"type": "HumanUser", "id": SG_USER["id"]},
                    "project": {"type": "Project", "id": SG_PROJECT["id"]},
                    "meta": {
                        "type": "attribute_change",
                        "attribute_name": "retirement_date",
                        "entity_type": "TimeLog",
                        "entity_id": SG_RETIRED_TIMELOG["id"],
                        "field_data_type": "entity",
                        "old_value": "2023-03-15",
                        "new_value": "2023-03-15",
                    },
                },
            )
        )

        self.assertEqual(len(bridge.jira.worklogs(issue.key)), 1)
        self.assertIn(worklog_1, bridge.jira.worklogs(issue.key))
        self.assertNotIn(worklog_2, bridge.jira.worklogs(issue.key))

        timelog_data = json.loads(issue.get_field(jira_field_id))
        self.assertIn(worklog_1.id, timelog_data)
        self.assertNotIn(worklog_2.id, timelog_data)

    def test_sg_to_jira_delete_timelog_flag_disabled(self, mocked_sg):
        """Test deleting a timelog in Flow Production Tracking when the delete flag is disabled"""

        syncer, bridge = self._get_syncer(mocked_sg, name="timelog_no_deletion")

        self.assertFalse(
            bridge.sync_in_jira(
                "timelog",
                "TimeLog",
                SG_TIMELOG["id"],
                {
                    "user": {"type": "HumanUser", "id": SG_USER["id"]},
                    "project": {"type": "Project", "id": SG_PROJECT["id"]},
                    "meta": {
                        "type": "attribute_change",
                        "attribute_name": "retirement_date",
                        "entity_type": "TimeLog",
                        "entity_id": SG_TIMELOG["id"],
                        "field_data_type": "entity",
                        "old_value": {
                            "name": "Fake Name",
                            "type": "HumanUser",
                            "id": 2,
                        },
                        "new_value": {
                            "name": SG_USER["name"],
                            "type": SG_USER["type"],
                            "id": SG_USER["id"],
                        },
                    },
                },
            )
        )

    def test_jira_to_sg_add_timelog(self, mocked_sg):
        """Test adding a new timelog in Jira"""

        syncer, bridge = self._get_syncer(mocked_sg, name="timelog")
        jira_field_id = bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_TIMELOG_FIELD)

        # mock the Jira data
        bridge.jira.set_projects([JIRA_PROJECT])
        issue = bridge.jira.create_issue({jira_field_id: ""})
        worklog = bridge.jira.add_worklog(
            issue,
            comment=SG_TIMELOG["description"],
            timeSpentSeconds=SG_TIMELOG["duration"] * 60,
            started=datetime.datetime.strptime(SG_TIMELOG["date"], "%Y-%m-%d").strftime(
                "%Y-%m-%dT%H:%M:%S.000+0000"
            ),
            author=bridge.jira.user(JIRA_USER_2["accountId"], "accountId"),
        )

        # mock the PTR data
        sg_task = SG_TASK.copy()
        sg_task[SHOTGUN_JIRA_ID_FIELD] = issue.key
        sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True

        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECT)
        self.add_to_sg_mock_db(bridge.shotgun, SG_USER)
        self.add_to_sg_mock_db(bridge.shotgun, SG_USER_2)
        self.add_to_sg_mock_db(bridge.shotgun, sg_task)

        self.assertTrue(
            bridge.sync_in_shotgun(
                "timelog",
                "Issue",
                "FAKED-01",
                {
                    "webhookEvent": "worklog_created",
                    "worklog": {
                        "author": {
                            "accountId": JIRA_USER_2["accountId"],
                        },
                        "issueId": issue.key,
                        "id": worklog.id,
                        "started": worklog.started,
                        "timeSpentSeconds": worklog.timeSpentSeconds,
                        "comment": worklog.comment,
                    },
                },
            )
        )

        sg_timelog = bridge.shotgun.find_one(
            "TimeLog",
            [[SHOTGUN_JIRA_ID_FIELD, "is", f"{issue.key}/{worklog.id}"]],
            list(SG_TIMELOG.keys()) + ["user.HumanUser.email"],
        )

        self.assertIsNotNone(sg_timelog)
        self.assertEqual(sg_timelog["description"], worklog.comment)
        self.assertEqual(
            sg_timelog["date"],
            datetime.datetime.strptime(
                worklog.started, "%Y-%m-%dT%H:%M:%S.%f%z"
            ).strftime("%Y-%m-%d"),
        )
        self.assertEqual(sg_timelog["duration"] * 60, worklog.timeSpentSeconds)
        self.assertEqual(
            sg_timelog["user.HumanUser.email"], JIRA_USER_2["emailAddress"]
        )

    def test_jira_to_sg_update_timelog(self, mocked_sg):
        """Test updating an existing timelog in Jira"""

        syncer, bridge = self._get_syncer(mocked_sg, name="timelog")
        jira_field_id = bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_TIMELOG_FIELD)

        # mock the Jira data
        bridge.jira.set_projects([JIRA_PROJECT])
        issue = bridge.jira.create_issue({jira_field_id: ""})
        worklog = bridge.jira.add_worklog(
            issue,
            comment=SG_TIMELOG["description"],
            timeSpentSeconds=SG_TIMELOG["duration"] * 60,
            started=datetime.datetime.strptime(SG_TIMELOG["date"], "%Y-%m-%d").strftime(
                "%Y-%m-%dT%H:%M:%S.000+0000"
            ),
            author=bridge.jira.user(JIRA_USER_2["accountId"], "accountId"),
        )

        # mock the PTR data
        sg_task = SG_TASK.copy()
        sg_task[SHOTGUN_JIRA_ID_FIELD] = issue.key
        sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True

        sg_timelog = SG_TIMELOG.copy()
        sg_timelog["duration"] = 0
        sg_timelog["description"] = "Fake comment"
        sg_timelog["date"] = "2023-03-15"
        sg_timelog["user"] = SG_USER_2
        sg_timelog[SHOTGUN_JIRA_ID_FIELD] = f"{issue.key}/{worklog.id}"

        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECT)
        self.add_to_sg_mock_db(bridge.shotgun, SG_USER)
        self.add_to_sg_mock_db(bridge.shotgun, SG_USER_2)
        self.add_to_sg_mock_db(bridge.shotgun, sg_task)
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog)

        self.assertTrue(
            bridge.sync_in_shotgun(
                "timelog",
                "Issue",
                "FAKED-01",
                {
                    "webhookEvent": "worklog_updated",
                    "worklog": {
                        "author": {
                            "accountId": JIRA_USER_2["accountId"],
                        },
                        "updateAuthor": {
                            "accountId": JIRA_USER_2["accountId"],
                        },
                        "issueId": issue.key,
                        "id": worklog.id,
                        "started": worklog.started,
                        "timeSpentSeconds": worklog.timeSpentSeconds,
                        "comment": worklog.comment,
                    },
                },
            )
        )

        sg_updated_timelog = bridge.shotgun.find_one(
            "TimeLog",
            [[SHOTGUN_JIRA_ID_FIELD, "is", f"{issue.key}/{worklog.id}"]],
            list(SG_TIMELOG.keys()) + ["user.HumanUser.email"],
        )

        self.assertIsNotNone(sg_timelog)
        self.assertEqual(sg_updated_timelog["description"], worklog.comment)
        self.assertEqual(
            sg_updated_timelog["date"],
            datetime.datetime.strptime(
                worklog.started, "%Y-%m-%dT%H:%M:%S.%f%z"
            ).strftime("%Y-%m-%d"),
        )
        self.assertEqual(sg_updated_timelog["duration"] * 60, worklog.timeSpentSeconds)

    def test_jira_to_sg_delete_timelog_flag_enabled(self, mocked_sg):
        """Test deleting a timelog in Jira when the delete flag is enabled"""

        syncer, bridge = self._get_syncer(mocked_sg, name="timelog")
        jira_field_id = bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_TIMELOG_FIELD)

        # mock the Jira data
        bridge.jira.set_projects([JIRA_PROJECT])
        issue = bridge.jira.create_issue({jira_field_id: ""})
        worklog = bridge.jira.add_worklog(
            issue,
        )

        # mock the PTR data
        sg_task = SG_TASK.copy()
        sg_task[SHOTGUN_JIRA_ID_FIELD] = issue.key
        sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True

        sg_timelog = SG_TIMELOG.copy()
        sg_timelog[SHOTGUN_JIRA_ID_FIELD] = f"{issue.key}/{worklog.id}"

        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECT)
        self.add_to_sg_mock_db(bridge.shotgun, SG_USER)
        self.add_to_sg_mock_db(bridge.shotgun, sg_task)
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog)

        self.assertTrue(
            bridge.sync_in_shotgun(
                "timelog",
                "Issue",
                "FAKED-01",
                {
                    "webhookEvent": "worklog_deleted",
                    "worklog": {
                        "id": worklog.id,
                        "issueId": issue.key,
                    },
                },
            )
        )

        sg_retired_timelog = bridge.shotgun.find_one(
            "TimeLog", [["id", "is", sg_timelog["id"]]]
        )
        self.assertIsNone(sg_retired_timelog)

    def test_jira_to_sg_delete_timelog_flag_disabled(self, mocked_sg):
        """Test deleting a timelog in Jira when the delete flag is disabled"""

        syncer, bridge = self._get_syncer(mocked_sg, name="timelog_no_deletion")

        self.assertFalse(
            bridge.sync_in_shotgun(
                "timelog",
                "Issue",
                "FAKED-01",
                {
                    "webhookEvent": "worklog_deleted",
                },
            )
        )

    def test_sync_existing_timelogs_and_worklogs(self, mocked_sg):
        """Test the sync of exisiting Flow Production Tracking timelogs and Jira worklogs"""

        syncer, bridge = self._get_syncer(mocked_sg, name="timelog")
        jira_tl_field_id = bridge.jira.get_jira_issue_field_id(
            JIRA_SHOTGUN_TIMELOG_FIELD
        )
        jira_sg_field_id = bridge.jira.get_jira_issue_field_id(JIRA_SHOTGUN_ID_FIELD)

        # mock the Jira data
        bridge.jira.set_projects([JIRA_PROJECT])
        issue = bridge.jira.create_issue(
            {jira_tl_field_id: "", jira_sg_field_id: SG_TASK["id"]}
        )

        worklog_1 = bridge.jira.add_worklog(
            issue,
            comment=SG_TIMELOG["description"],
            timeSpentSeconds=SG_TIMELOG["duration"] * 60,
            started=datetime.datetime.strptime(SG_TIMELOG["date"], "%Y-%m-%d").strftime(
                "%Y-%m-%dT%H:%M:%S.000+0000"
            ),
            author=bridge.jira.user(JIRA_USER_2["accountId"], "accountId"),
        )

        worklog_2 = bridge.jira.add_worklog(
            issue,
            comment=SG_TIMELOG["description"],
            timeSpentSeconds=SG_TIMELOG["duration"] * 60,
            started=datetime.datetime.strptime(SG_TIMELOG["date"], "%Y-%m-%d").strftime(
                "%Y-%m-%dT%H:%M:%S.000+0000"
            ),
            author=bridge.jira.user(JIRA_USER_2["accountId"], "accountId"),
        )

        # mock the PTR data
        sg_task = SG_TASK.copy()
        sg_task[SHOTGUN_JIRA_ID_FIELD] = issue.key
        sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD] = True

        sg_timelog_1 = SG_TIMELOG.copy()
        sg_timelog_1["entity"] = sg_task

        sg_timelog_2 = SG_TIMELOG.copy()
        sg_timelog_2["id"] = 2
        sg_timelog_2["entity"] = sg_task
        sg_timelog_2[SHOTGUN_JIRA_ID_FIELD] = f"{issue.key}/{worklog_2.id}"

        self.add_to_sg_mock_db(bridge.shotgun, SG_PROJECT)
        self.add_to_sg_mock_db(bridge.shotgun, SG_USER)
        self.add_to_sg_mock_db(bridge.shotgun, SG_USER_2)
        self.add_to_sg_mock_db(bridge.shotgun, sg_task)
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog_1)
        self.add_to_sg_mock_db(bridge.shotgun, sg_timelog_2)

        self.assertTrue(
            bridge.sync_in_jira(
                "timelog",
                "Task",
                SG_TASK["id"],
                {
                    "user": {"type": "HumanUser", "id": SG_USER["id"]},
                    "project": {"type": "Project", "id": SG_PROJECT["id"]},
                    "meta": {
                        "type": "attribute_change",
                        "attribute_name": SHOTGUN_SYNC_IN_JIRA_FIELD,
                        "entity_type": "Task",
                        "entity_id": SG_TASK["id"],
                        "field_data_type": "entity",
                        "old_value": False,
                        "new_value": True,
                    },
                },
            )
        )

        sg_timelog_added = bridge.shotgun.find_one(
            "TimeLog", [[SHOTGUN_JIRA_ID_FIELD, "is", f"{issue.key}/{worklog_1.id}"]]
        )

        sg_timelog_updated = bridge.shotgun.find_one(
            "TimeLog", [["id", "is", sg_timelog_1["id"]]], [SHOTGUN_JIRA_ID_FIELD]
        )

        self.assertEqual(len(bridge.jira.worklogs(issue.key)), 3)
        self.assertIsNotNone(sg_timelog_added)
        self.assertIsNotNone(sg_timelog_updated[SHOTGUN_JIRA_ID_FIELD])

        jira_worklog_key = sg_timelog_updated[SHOTGUN_JIRA_ID_FIELD].split("/")[1]
        self.assertIsNotNone(bridge.jira.worklog(issue.key, jira_worklog_key))
        timelog_data = json.loads(issue.get_field(jira_tl_field_id))
        self.assertEqual(timelog_data[jira_worklog_key]["user"]["id"], SG_USER["id"])
