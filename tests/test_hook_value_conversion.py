# -*- coding: utf-8 -*-

# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import logging
import unittest
from unittest import mock

import jira

from sg_jira.errors import InvalidJiraValue
from sg_jira.hook import JiraHook


def _props(name="duration", data_type="duration"):
    """Minimal ``sg_field_properties`` dict consumed by the converter."""
    return {"name": {"value": name}, "data_type": {"value": data_type}}


class TestDurationConversion(unittest.TestCase):
    """``get_sg_value_from_jira_value`` for the duration/number data types."""

    def setUp(self):
        self.hook = JiraHook(bridge=mock.Mock(), logger=logging.getLogger("test"))

    def _convert(self, jira_value, jira_entity=None, data_type="duration"):
        return self.hook.get_sg_value_from_jira_value(
            jira_value, jira_entity, None, _props(data_type=data_type)
        )

    def test_falsy_value_returns_zero(self):
        for value in (0, None, "", []):
            self.assertEqual(self._convert(value), 0)

    def test_timetracking_resource_uses_original_estimate_seconds(self):
        # Issue.timetracking is a TimeTracking resource, not a scalar; the
        # numeric value is in originalEstimateSeconds and is reported in minutes.
        tt = mock.Mock(spec=jira.resources.TimeTracking)
        tt.originalEstimateSeconds = 3600
        self.assertEqual(self._convert(tt), 60)

    def test_timetracking_resource_without_estimate_returns_zero(self):
        tt = mock.Mock(spec=jira.resources.TimeTracking)
        tt.originalEstimateSeconds = None
        self.assertEqual(self._convert(tt), 0)

    def test_worklog_entity_uses_time_spent_seconds(self):
        # Worklog.timeSpent is a display string ("1h 30m"); the numeric value
        # lives on the Worklog's timeSpentSeconds attribute, reported in minutes.
        worklog = mock.Mock(spec=jira.resources.Worklog)
        worklog.timeSpentSeconds = 5400
        self.assertEqual(self._convert("1h 30m", jira_entity=worklog), 90)

    def test_plain_integer_value_passed_through(self):
        self.assertEqual(self._convert(5, data_type="number"), 5)

    def test_unparseable_string_raises(self):
        with self.assertRaises(InvalidJiraValue):
            self._convert("abc", data_type="number")

    def test_non_numeric_type_raises(self):
        # A truthy, non-int value (e.g. a list) hits int()'s TypeError, which
        # the converter now maps to InvalidJiraValue alongside ValueError.
        with self.assertRaises(InvalidJiraValue):
            self._convert([1, 2], data_type="number")


if __name__ == "__main__":
    unittest.main()
