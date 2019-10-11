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
import threading

from shotgun_api3 import Shotgun
from jira import JIRA

from unittest2 import TestCase

import webapp

# Inspired by https://docs.python.org/2/library/basehttpserver.html#more-examples
class ServerThread(threading.Thread):
    """
    Thread that spawns the jira bridge server.

    When stop is invoked, the bridge is closed.
    """
    def __init__(self):
        """
        init.
        """
        super(ServerThread, self).__init__()
        self._httpd = webapp.create_server(
            9090,
            os.path.join(os.path.dirname(__file__), "bridge_settings.py"),
        )

    def run(self):
        """
        Handles requests until the server is closed.
        """
        try:
            self._httpd.serve_forever()
        except Exception:
            # Simply swallow the error that will be raised here because of the
            # socket closure.
            pass

    def stop(self):
        """
        Stop the server.
        """
        # We're closing the socket violently, since handle_request is a blocking
        # call.
        try:
            self._httpd.socket.close()
        except:
            pass

class TestIntegration(TestCase):

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

    def _expect(self, functor, description=None, max_time=20.0):
        """
        Try a executing successfully a functor for the given number of seconds
        until it stops raising an error.
        """
        before = time.time()

        try:
            return functor()
        except Exception:
            pass

        nb_tries = 2
        while True:
            time.sleep(1)
            print(
                "Retrying '{0}'({1})...".format(
                    description or functor.__name__, nb_tries
                )
            )
            try:
                return functor()
            except Exception:
                if (before + max_time) > time.time():
                    nb_tries += 1
                else:
                    raise

    def _get_jira_key(self, entity):
        def wait_for_jira_key():
            result = self._sg.find_one(
                entity["type"], [["id", "is", entity["id"]]], ["sg_jira_key"]
            )
            self.assertIsNotNone(result["sg_jira_key"])
            return result["sg_jira_key"]

        return self._expect(wait_for_jira_key)

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
        thread = ServerThread()
        # Ideally the thread start/top would be done in setUp/tearDown, but when hitting
        # CTRL-C to end the tests the tearDown handlers are not invoked. This would
        # leave the process handing because there is still a thread running.
        try:
            thread.start()
            self._test_create_task()
            # self._update_status_from_shotgun()
            # self._update_status_from_jira()
            self._test_update_assignment_from_shotgun()
            self._test_update_assignment_from_jira()
        finally:
            thread.stop()

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
            self.assertEqual(self._issue.fields.status.name, "In Progress")

        self._sg.update("Task", self._sg_task["id"], {"sg_status_list": "ip"})
        self._expect(wait_for_issue_in_progress)

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
            self.assertEqual(task["sg_status_list"], "fin")

        self._set_jira_status(self._issue, "Done")
        self._expect(wait_for_shotgun_status_final)

    def _test_update_assignment_from_shotgun(self):
        def wait_for_assignee_to_change(expected_user_id):
            self.assertEqual(
                getattr(self._issue.fields.assignee, self.USER_ID_FIELD),
                expected_user_id,
            )

        # Assign the ticket to a user in Shotgun
        self._sg.update(
            "Task", self._sg_task["id"], {"task_assignees": [self._sg_user_1]}
        )

        # Make sure
        self._expect(
            lambda: wait_for_assignee_to_change(self._jira_user_1),
            "wait_for_assignee_to_change_to_1",
        )

        self._sg.update(
            "Task", self._sg_task["id"], {"task_assignees": [self._sg_user_2]}
        )
        self._expect(
            lambda: wait_for_assignee_to_change(self._jira_user_2),
            "wait_for_assignee_to_change_to_2",
        )

        # TODO: Understand how the bridge deals with multiple task assignees and how
        # it decides which one gets set on the JIRA ticket.

        # self._sg.update(
        #     "Task", self._sg_task["id"], {"task_assignees": [self._sg_user_1, self._sg_user_2]}
        # )
        # self._expect(lambda: wait_for_assignee_to_change(self._jira_user_2), "wait_for_assignee_to_change_to_2")

    def _test_update_assignment_from_jira(self):
        pass
