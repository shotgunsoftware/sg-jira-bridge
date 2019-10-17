# -*- coding: utf-8 -*-
# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import mock

from sg_jira.handlers.entity_issue_handler import EntityIssueHandler

from unittest2 import TestCase


class TestHierarchySyncer(TestCase):
    """
    Test hierarchy syncer example.
    """

    def test_jira_cloud_accound_regex(self):
        """
        Test syncing links from SG to Jira.
        """
        # These are the two formats we're aware of for account id's in JIRA.
        self.assertIsNotNone(
            EntityIssueHandler.ACCOUNT_ID_RE.match(
                "123456:60e119d8-6a49-4375-95b6-6740fc8e75e0"
            )
        )
        self.assertIsNotNone(
            EntityIssueHandler.ACCOUNT_ID_RE.match("5b6a25ab7c14b729f2208297")
        )
        self.assertIsNone(EntityIssueHandler.ACCOUNT_ID_RE.match("joe.smith"))
