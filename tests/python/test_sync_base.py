# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os

from shotgun_api3.lib import mockgun
import sg_jira

from test_base import TestBase


class ExtMockgun(mockgun.Shotgun):
    """
    Add missing mocked methods to mockgun.Shotgun
    """
    def add_user_agent(*args, **kwargs):
        pass

    def set_session_uuid(*args, **kwargs):
        pass


class TestSyncBase(TestBase):
    """
    Base class for syncing tests.

    All classes deriving from this one should use the `@mock.patch("shotgun_api3.Shotgun")`
    class decorator to mock Shotgun with mockgun.
    This works only if the code uses shotgun_api3.Shotgun and does not
    `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`

    All test methods will have an extra mocked_sg parameter.
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

    def _get_syncer(self, mocked_sg, name="task_issue"):
        """
        Helper to get a syncer and a bridge with a mocked Shotgun.

        :param mocked_sg: Mocked shotgun_api3.Shotgun.
        :parma str name: A syncer name.
        """

        mocked_sg.return_value = self._get_mocked_sg_handle()
        bridge = sg_jira.Bridge.get_bridge(
            os.path.join(self._fixtures_path, "settings.py")
        )
        syncer = bridge.get_syncer(name)
        return syncer, bridge

    def setUp(self):
        """
        Test setup.
        """
        super(TestSyncBase, self).setUp()
        self.set_sg_mock_schema(os.path.join(
            self._fixtures_path,
            "schemas", "sg-jira",
        ))

        self.mock_jira_session_bases()

        # TODO: add a Shotgun patcher so deriving classes don't have to patch
        # Shotgun themselves.
