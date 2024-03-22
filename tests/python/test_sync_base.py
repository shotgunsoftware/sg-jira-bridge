# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import datetime
import os

from shotgun_api3 import ShotgunError
from shotgun_api3.lib import mockgun, six
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

    def _validate_entity_data(self, entity_type, data):
        """Workaround to fix the right date type. This should be moved to the API itself..."""
        if "id" in data or "type" in data:
            raise ShotgunError("Can't set id or type on create or update")

        self._validate_entity_fields(entity_type, data.keys())

        for field, item in data.items():

            if item is None:
                # none is always ok
                continue

            field_info = self._schema[entity_type][field]

            if field_info["data_type"]["value"] == "multi_entity":
                if not isinstance(item, list):
                    raise ShotgunError(
                        "%s.%s is of type multi_entity, but data %s is not a list"
                        % (entity_type, field, item)
                    )
                elif item and any(not isinstance(sub_item, dict) for sub_item in item):
                    raise ShotgunError(
                        "%s.%s is of type multi_entity, but data %s contains a non-dictionary"
                        % (entity_type, field, item)
                    )
                elif item and any(
                    "id" not in sub_item or "type" not in sub_item for sub_item in item
                ):
                    raise ShotgunError(
                        "%s.%s is of type multi-entity, but an item in data %s does not contain 'type' and 'id'"
                        % (entity_type, field, item)
                    )
                elif item and any(
                    sub_item["type"]
                    not in field_info["properties"]["valid_types"]["value"]
                    for sub_item in item
                ):
                    raise ShotgunError(
                        "%s.%s is of multi-type entity, but an item in data %s has an invalid type (expected one of %s)"
                        % (
                            entity_type,
                            field,
                            item,
                            field_info["properties"]["valid_types"]["value"],
                        )
                    )

            elif field_info["data_type"]["value"] == "entity":
                if not isinstance(item, dict):
                    raise ShotgunError(
                        "%s.%s is of type entity, but data %s is not a dictionary"
                        % (entity_type, field, item)
                    )
                elif "id" not in item or "type" not in item:
                    raise ShotgunError(
                        "%s.%s is of type entity, but data %s does not contain 'type' and 'id'"
                        % (entity_type, field, item)
                    )
            else:
                try:
                    sg_type = field_info["data_type"]["value"]
                    python_type = {
                        "number": int,
                        "float": float,
                        "checkbox": bool,
                        "percent": int,
                        "text": six.string_types,
                        "serializable": dict,
                        "entity_type": six.string_types,
                        "date": six.string_types,
                        "date_time": datetime.datetime,
                        "list": six.string_types,
                        "status_list": six.string_types,
                        "duration": int,
                        "url": dict,
                    }[sg_type]
                except KeyError:
                    raise ShotgunError(
                        "Field %s.%s: Handling for Flow Production Tracking type %s is not implemented"
                        % (entity_type, field, sg_type)
                    )

                if not isinstance(item, python_type):
                    raise ShotgunError(
                        "%s.%s is of type %s, but data %s is not of type %s"
                        % (entity_type, field, type(item), sg_type, python_type)
                    )

                # TODO: add check for correct timezone


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
        Return a mocked PTR handle.
        """
        return ExtMockgun(
            "https://mocked.my.com",
            "Ford Prefect",
            "xxxxxxxxxx",
        )

    def _get_syncer(self, mocked_sg, name="task_issue"):
        """
        Helper to get a syncer and a bridge with a mocked Flow Production Tracking.

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
        self.set_sg_mock_schema(
            os.path.join(
                self._fixtures_path,
                "schemas",
                "sg-jira",
            )
        )

        self.mock_jira_session_bases()

        # TODO: add a Shotgun patcher so deriving classes don't have to patch
        # Shotgun themselves.
