# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import unittest2 as unittest
import mock
from shotgun_api3.lib import mockgun
from shotgun_api3 import Shotgun

from test_base import TestBase

import sg_jira

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
    def test_project_match(self, mocked):
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
        #raise ValueError(dir(sg_jira))
        syncer = bridge.get_syncer("default")
        jira_projects = bridge._jira.projects()
        syncer.match_jira_ressource("Project", 1, jira_projects[0].name)
