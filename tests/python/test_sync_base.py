# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os

from shotgun_api3.lib import mockgun
from test_base import TestBase

import sg_jira


class TestSyncBase(TestBase):
    """
    Base class for syncing tests.

    All classes deriving from this one should use the `@mock.patch("shotgun_api3.Shotgun")`
    class decorator to mock Shotgun with mockgun.
    This works only if the code uses shotgun_api3.Shotgun and does not
    `from shotgun_api3 import Shotgun` and then `sg = Shotgun(...)`

    All test methods will have an extra mocked_sg parameter.
    """

    def _get_syncer(self, mocked_sg, name="task_issue"):
        """
        Helper to get a syncer and a bridge with a mocked Flow Production Tracking.

        :param mocked_sg: Mocked shotgun_api3.Shotgun.
        :parma str name: A syncer name.
        """
        mocked_sg.return_value = mockgun.Shotgun(
            "https://mocked.my.com",
            "Ford Prefect",
            "xxxxxxxxxx",
        )
        bridge = sg_jira.Bridge.get_bridge(
            os.path.join(self._fixtures_path, "settings.py")
        )
        syncer = bridge.get_syncer(name)
        return syncer, bridge

    def setUp(self):
        """
        Test setup.
        """
        super().setUp()
        self.set_sg_mock_schema(
            os.path.join(
                self._fixtures_path,
                "schemas",
                "sg-jira",
            )
        )

        self.mock_jira_session_bases()

        # Patch mockgun.Shotgun with no-op stubs for real SG API methods that
        # mockgun doesn't implement (add_user_agent added in SG-42067,
        # set_session_uuid called by bridge.sync_in_jira).
        for _method in ("add_user_agent", "set_session_uuid"):
            if not hasattr(mockgun.Shotgun, _method):
                setattr(mockgun.Shotgun, _method, lambda self, *a, **kw: None)
                self.addCleanup(delattr, mockgun.Shotgun, _method)

        # mockgun's _validate_entity_data doesn't know about the SG "duration"
        # data type (used by TimeLog.duration). Patch it to treat duration as
        # number (int), which is how the SG Python API stores duration values.
        _orig_validate = mockgun.Shotgun._validate_entity_data

        def _validate_with_duration(self_mg, entity_type, data):
            for field in list(data):
                fi = self_mg._schema.get(entity_type, {}).get(field, {})
                if fi.get("data_type", {}).get("value") == "duration":
                    fi["data_type"]["value"] = "number"
            _orig_validate(self_mg, entity_type, data)

        mockgun.Shotgun._validate_entity_data = _validate_with_duration
        self.addCleanup(
            setattr, mockgun.Shotgun, "_validate_entity_data", _orig_validate
        )

        # TODO: add a Shotgun patcher so deriving classes don't have to patch
        # Shotgun themselves.
