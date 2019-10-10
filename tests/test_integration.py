# -*- coding: utf-8 -*-

# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

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
            password=os.environ["SGJIRA_TEST_SG_PASSWORD"]
        )

        cls._jira = JIRA(
            os.environ["SGJIRA_JIRA_SITE"],
            basic_auth=(os.environ["SGJIRA_JIRA_TEST_USER"], os.environ["SGJIRA_JIRA_TEST_USER_SECRET"])
        )

        cls._sg_project = {
            "type": "Project",
            "id": int(os.environ["SGJIRA_TEST_SG_PROJECT_ID"])
        }
        cls._jira_project = os.environ["SGJIRA_TEST_JIRA_PROJECT_KEY"]

        cls._sg_user_1 = cls._sg.find_one(
            "HumanUser", [["login", "is", os.environ["SGJIRA_TEST_SG_USER"]]]
        )
        cls._sg_user_2 = cls._sg.find_one(
            "HumanUser", [["id", "is", int(os.environ["SGJIRA_TEST_SG_USER_2"])]]
        )

        cls._jira_user_1 = cls._jira.myself()[cls.USER_ID_FIELD]
        #cls._jira_user_2 = cls._jira.myself()[cls.USER_ID_FIELD]

    def _try_for(self, functor, max_time=10.0):
        before = time.time()

        result = functor()
        if result is not None:
            return result

        nb_tries = 2
        while (before + max_time) > time.time():
            time.sleep(1)
            print("Retrying ({0})...".format(nb_tries))
            result = functor()
            if result is not None:
                return result
            nb_tries += 1
            
        raise RuntimeError("Did not complete under {0} seconds.".format(max_time))

    def _get_jira_key(self, entity):

        def functor():
            result = self._sg.find_one(entity["type"], [["id", "is", entity["id"]]], ["sg_jira_key"])
            return None if result["sg_jira_key"] is None else result["sg_jira_key"]

        return self._try_for(functor)
        

    def _create_task(self, name):
        new_sg_task = self._sg.create("Task", {"content": name, "sg_sync_in_jira": True, "project": self._sg_project })
        jira_key = self._get_jira_key(new_sg_task)
        pdb.set_trace()
        return new_sg_task, jira_key
        
    def test_integration(self):
        """
        Test the integration.
        """
        self._test_create_task()
        self._update_status_from_shotgun()
        self._update_status_from_jira()

    def _test_create_task(self):
        # Create a task and make sure it gets synced across
        self._sg_task, self._jira_key = self._create_task("Test")
        issue = self._jira.issue(self._jira_key)
        self.assertEqual(issue.raw["fields"]["reporter"][self.USER_ID_FIELD], self._jira_user_1)
        
    def _update_status_from_shotgun(self):
        self._sg.update("Task", self._sg_task["id"], {"sg_status_list": "ip"})

        def functor():
            issue = self._jira.issue(self._jira_key)
            if issue.fields.status == "In Progress":
                return issue
            else:
                return None

        issue = self._try_for(functor)
        self.assertEqual(issue.fields.status, "In Progress")
        
    def _update_status_from_jira(self):
        pass #self._jira.
