# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import unittest

from mock_jira import MockedJira
from shotgun_api3.lib import mockgun

from sg_jira.jira_session import JiraSession


class TestBase(unittest.TestCase):
    """
    A TestCase class with some helpers to mock PTR calls.
    """

    def setUp(self):
        super(TestBase, self).setUp()
        self._fixtures_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "fixtures")
        )

    def mock_jira_session_bases(self):
        """
        Replace the JiraSession base class to be MockedJira
        so we can run tests without an actual connection to
        JIRA.
        """
        # Do not use mock.patcher for this, as the patcher's exit
        # method will try to delete the bases before restoring them,
        # which will raise an error.
        self.__old_bases = JiraSession.__bases__
        JiraSession.__bases__ = (MockedJira,)

        def restore_bases():
            JiraSession.__bases__ = self.__old_bases

        self.addCleanup(restore_bases)

    def set_sg_mock_schema(self, path):
        """
        Set the PTR mock schema from files in the given folder.

        :param str path: A folder path which contains schema pickle files.
        """
        mockgun_schema_path = os.path.join(path, "schema.pickle")
        mockgun_schema_entity_path = os.path.join(path, "schema_entity.pickle")
        mockgun.Shotgun.set_schema_paths(
            mockgun_schema_path, mockgun_schema_entity_path
        )

    def add_to_sg_mock_db(self, mockgun, entities):
        """
        Adds an entity or entities to the mocked Flow Production Tracking database.
        :param entities: A Flow Production Tracking style dictionary with keys for id, type, and name
                         defined. A list of such dictionaries is also valid.
        """
        # make sure it's a list
        if isinstance(entities, dict):
            entities = [entities]
        for src_entity in entities:
            # Make a copy
            entity = dict(src_entity)
            # entity: {"id": 2, "type":"Shot", "name":...}
            # wedge it into the mockgun database
            et = entity["type"]
            eid = entity["id"]

            # special retired flag for mockgun
            if "__retired" not in entity:
                entity["__retired"] = False
            # set a created by
            entity["created_by"] = {"type": "HumanUser", "id": 1}
            # turn any dicts into proper type/id/name refs
            for x in entity:
                # special case: EventLogEntry.meta is not an entity link dict
                if isinstance(entity[x], dict) and x != "meta":
                    # make a std sg link dict with name, id, type
                    link_dict = {"type": entity[x]["type"], "id": entity[x]["id"]}

                    # most basic case is that there already is a name field,
                    # in that case we are done
                    if "name" in entity[x]:
                        link_dict["name"] = entity[x]["name"]

                    elif entity[x]["type"] == "Task":
                        # task has a 'code' field called content
                        link_dict["name"] = entity[x]["content"]

                    elif "code" not in entity[x]:
                        # auto generate a code field
                        link_dict["name"] = "mockgun_autogenerated_%s_id_%s" % (
                            entity[x]["type"],
                            entity[x]["id"],
                        )

                    else:
                        link_dict["name"] = entity[x]["code"]

                    # print "Swapping link dict %s -> %s" % (entity[x], link_dict)
                    entity[x] = link_dict

            mockgun._db[et][eid] = entity
