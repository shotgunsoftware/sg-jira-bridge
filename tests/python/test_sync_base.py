# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import mock


from shotgun_api3.lib import mockgun
from mock_jira import MockedJira, JIRA_USER
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

        # Mocks the current_user_id which depends on introspecting
        # data coming back from the JIRA API and that we won't
        # simulate for these tests.
        patcher = mock.patch.object(
            sg_jira.jira_session.JiraSession,
            "current_user_id",
            lambda _: JIRA_USER["accountId"]
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        # Patch the JiraSession base class to use our MockedJira instead of
        # the jira.client.Jira class.
        patcher = mock.patch.object(
            sg_jira.jira_session.JiraSession,
            "__bases__",
            (MockedJira,)
        )
        patcher.is_local = True
        patcher.start()
        # FIXME: the patcher fails with TypeError: can't delete JiraSession.__bases__
        # in its __exit__. We don't need the original jira.client.Jira class
        # in these tests, so restoring it is not an issue, but this is not
        # clean and should be fixed.
        # self.addCleanup(patcher.stop)

        # TODO: add a Shotgun patcher so deriving classes don't have to patch
        # Shotgun themselves.
