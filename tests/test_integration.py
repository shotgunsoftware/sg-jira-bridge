# -*- coding: utf-8 -*-

# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from pprint import pprint
import os
import time
import pdb

from shotgun_api3 import Shotgun
from jira import JIRA

from unittest2 import TestCase


class InterationTest(TestCase):

    USER_ID_FIELD = "key"

    @classmethod
    def setUpClass(cls):
        cls._sg = Shotgun(
            os.environ["SGJIRA_SG_SITE"],
            login=os.environ["SGJIRA_TEST_SG_USER"],
            password=os.environ["SGJIRA_TEST_SG_PASSWORD"],
        )

        cls._jira = JIRA(
            os.environ["SGJIRA_JIRA_SITE"],
            basic_auth=(
                os.environ["SGJIRA_JIRA_TEST_USER"],
                os.environ["SGJIRA_JIRA_TEST_USER_SECRET"],
            ),
        )

        cls._sg_project = {
            "type": "Project",
            "id": int(os.environ["SGJIRA_TEST_SG_PROJECT_ID"]),
        }
        cls._jira_project = os.environ["SGJIRA_TEST_JIRA_PROJECT_KEY"]

        cls._sg_user_1 = cls._sg.find_one(
            "HumanUser", [["login", "is", os.environ["SGJIRA_TEST_SG_USER"]]]
        )
        cls._sg_user_2 = cls._sg.find_one(
            "HumanUser", [["id", "is", int(os.environ["SGJIRA_TEST_SG_USER_2"])]]
        )

        cls._jira_user_1 = cls._jira.myself()[cls.USER_ID_FIELD]
        cls._jira_user_2 = os.environ["SGJIRA_JIRA_TEST_USER_2"]

    def _try_for(self, functor, description=None, max_time=20.0):
        before = time.time()

        result = functor()
        if result is not None:
            return result

        nb_tries = 2
        while (before + max_time) > time.time():
            time.sleep(1)
            print("Retrying '{0}'({1})...".format(description or functor.__name__, nb_tries))
            result = functor()
            if result is not None:
                return result
            nb_tries += 1

        raise RuntimeError("Did not complete under {0} seconds.".format(max_time))

    def _get_jira_key(self, entity):
        def wait_for_jira_key():
            result = self._sg.find_one(
                entity["type"], [["id", "is", entity["id"]]], ["sg_jira_key"]
            )
            return None if result["sg_jira_key"] is None else result["sg_jira_key"]

        return self._try_for(wait_for_jira_key)

    def _create_task(self, name):
        new_sg_task = self._sg.create(
            "Task",
            {"content": name, "sg_sync_in_jira": True, "project": self._sg_project},
        )
        jira_key = self._get_jira_key(new_sg_task)
        return new_sg_task, jira_key

    def test_integration(self):
        """
        Test the integration.
        """
        self._test_create_task()
        # self._update_status_from_shotgun()
        # self._update_status_from_jira()
        # self._test_update_assignment_from_shotgun()
        self._test_update_assignment_from_jira()

    def _test_create_task(self):
        # Create a task and make sure it gets synced across
        self._sg_task, self._jira_key = self._create_task("Test")
        self.assertEqual(
            getattr(self._issue.fields.reporter, self.USER_ID_FIELD), self._jira_user_1
        )

    @property
    def _issue(self):
        return self._jira.issue(self._jira_key)

    def _update_status_from_shotgun(self):
        def wait_for_issue_in_progress():
            issue = self._issue
            if issue.fields.status.name == "In Progress":
                return issue
            else:
                return None

        self._sg.update("Task", self._sg_task["id"], {"sg_status_list": "ip"})
        issue = self._try_for(wait_for_issue_in_progress)
        self.assertEqual(issue.fields.status.name, "In Progress")

    def _set_jira_status(self, issue, status_name):
        jira_transitions = self._jira.transitions(issue, expand="transitions.fields")
        for tra in jira_transitions:
            # Match a transition with the expected status name
            if tra["to"]["name"] == status_name:
                break
        else:
            raise RuntimeError("No transitions found for {0}!", status_name)

        self._jira.transition_issue(self._issue, tra["id"])

    def _update_status_from_jira(self):
        def wait_for_shotgun_status_final():
            task = self._sg.find_one(
                "Task", [["id", "is", self._sg_task["id"]]], ["sg_status_list"]
            )
            if task["sg_status_list"] == "fin":
                return task
            else:
                return None

        self._set_jira_status(self._issue, "Done")
        task = self._try_for(wait_for_shotgun_status_final)
        self.assertEqual(task["sg_status_list"], "fin")

    def _test_update_assignment_from_shotgun(self):
        def wait_for_assignee_to_change(expected_user_id):
            assignee = self._issue.fields.assignee
            if not assignee:
                return None
            user_id = getattr(assignee, self.USER_ID_FIELD)
            if user_id == expected_user_id:
                return user_id
            else:
                return None

        # Assign the ticket to a user in Shotgun
        self._sg.update(
            "Task", self._sg_task["id"], {"task_assignees": [self._sg_user_1]}
        )

        # Make sure
        user_id = self._try_for(lambda: wait_for_assignee_to_change(self._jira_user_1), "wait_for_assignee_to_change_to_1")
        self.assertEqual(user_id, self._jira_user_1)

        self._sg.update(
            "Task", self._sg_task["id"], {"task_assignees": [self._sg_user_2]}
        )
        user_id = self._try_for(lambda: wait_for_assignee_to_change(self._jira_user_2), "wait_for_assignee_to_change_to_2")

    def _test_update_assignment_from_jira(self):
        pass
