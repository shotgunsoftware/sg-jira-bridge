# -*- coding: utf-8 -*-

# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import re
import six

from test_base import TestBase
import sg_jira

UNICODE_STRING = u"unicode_îéö_😀"
UTF8_ENCODED_STRING = six.ensure_str(UNICODE_STRING)


class TestUtils(TestBase):
    """
    Test various utilities.
    """

    def test_utf8_to_unicode(self):
        """
        Test utf8 decoding.
        """
        # Unicode value should be unchanged
        res = sg_jira.utils.utf8_to_unicode(UNICODE_STRING)
        self.assertEqual(res, UNICODE_STRING)

        # Utf-8 encoded string should be decoded
        res = sg_jira.utils.utf8_to_unicode(UTF8_ENCODED_STRING)
        self.assertEqual(res, UNICODE_STRING)

        # All values in a list should be decoded if needed
        res = sg_jira.utils.utf8_to_unicode(
            [UTF8_ENCODED_STRING, UNICODE_STRING, UTF8_ENCODED_STRING]
        )
        self.assertEqual(res, [UNICODE_STRING, UNICODE_STRING, UNICODE_STRING])

        # All keys and values in a dict should be decoded if needed
        res = sg_jira.utils.utf8_to_unicode(
            {
                UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
                "foo": UNICODE_STRING,
                "blah": 1,
                "%s_bis" % UNICODE_STRING: UTF8_ENCODED_STRING,
            }
        )
        self.assertEqual(
            res,
            {
                UNICODE_STRING: UNICODE_STRING,
                "foo": UNICODE_STRING,
                "blah": 1,
                "%s_bis" % UNICODE_STRING: UNICODE_STRING,
            },
        )
        # Check that conflicts between a decoded key and an existing one are
        # correctly detected.
        with self.assertRaises(ValueError) as cm:
            # Note: we can't use self.assertRaisesRegexp which calls `str` on
            # the error message to perform the match, and fails with UnicodeEncodeError.
            sg_jira.utils.utf8_to_unicode(
                {
                    UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
                    "foo": UNICODE_STRING,
                    "blah": 1,
                    UNICODE_STRING: UTF8_ENCODED_STRING,
                }
            )
        self.assertIsNotNone(
            re.match(
                "UTF-8 decoded key %s is already present in dictionary being decoded"
                % UNICODE_STRING,
                cm.exception.message,
            )
        )
        # A dictionary with lists
        res = sg_jira.utils.utf8_to_unicode(
            {
                UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
                "foo": [UTF8_ENCODED_STRING, UNICODE_STRING, UTF8_ENCODED_STRING],
                "blah": [1, 2, 3, 4],
                "%s_bis"
                % UNICODE_STRING: [
                    UTF8_ENCODED_STRING,
                    UNICODE_STRING,
                    UTF8_ENCODED_STRING,
                ],
            }
        )
        self.assertEqual(
            res,
            {
                UNICODE_STRING: UNICODE_STRING,
                "foo": [UNICODE_STRING, UNICODE_STRING, UNICODE_STRING],
                "blah": [1, 2, 3, 4],
                "%s_bis"
                % UNICODE_STRING: [UNICODE_STRING, UNICODE_STRING, UNICODE_STRING],
            },
        )
        # A list of dictionaries
        d = {
            UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
            "foo": [UTF8_ENCODED_STRING, UNICODE_STRING, UTF8_ENCODED_STRING],
            "blah": [1, 2, 3, 4],
            "%s_bis"
            % UNICODE_STRING: [
                UTF8_ENCODED_STRING,
                UNICODE_STRING,
                UTF8_ENCODED_STRING,
            ],
        }
        res = sg_jira.utils.utf8_to_unicode([d] * 7)
        decoded = {
            UNICODE_STRING: UNICODE_STRING,
            "foo": [UNICODE_STRING, UNICODE_STRING, UNICODE_STRING],
            "blah": [1, 2, 3, 4],
            "%s_bis" % UNICODE_STRING: [UNICODE_STRING, UNICODE_STRING, UNICODE_STRING],
        }
        self.assertEqual(res, [decoded] * 7)
        # Nested dictionaries lists and tuples
        d = {
            UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
            "foo": (UTF8_ENCODED_STRING, UNICODE_STRING, UTF8_ENCODED_STRING),
            "blah": [1, 2, 3, 4],
            "%s_bis"
            % UNICODE_STRING: [
                UTF8_ENCODED_STRING,
                {
                    UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
                    "foo": [UTF8_ENCODED_STRING, UNICODE_STRING, UTF8_ENCODED_STRING],
                    "blah": [1, 2, 3, 4],
                    "%s_bis"
                    % UNICODE_STRING: [
                        UTF8_ENCODED_STRING,
                        UNICODE_STRING,
                        UTF8_ENCODED_STRING,
                    ],
                },
                UNICODE_STRING,
                UTF8_ENCODED_STRING,
            ],
        }
        res = sg_jira.utils.utf8_to_unicode(d)
        decoded = {
            UNICODE_STRING: UNICODE_STRING,
            "foo": (UNICODE_STRING, UNICODE_STRING, UNICODE_STRING),
            "blah": [1, 2, 3, 4],
            "%s_bis"
            % UNICODE_STRING: [
                UNICODE_STRING,
                {
                    UNICODE_STRING: UNICODE_STRING,
                    "foo": [UNICODE_STRING, UNICODE_STRING, UNICODE_STRING],
                    "blah": [1, 2, 3, 4],
                    "%s_bis"
                    % UNICODE_STRING: [UNICODE_STRING, UNICODE_STRING, UNICODE_STRING],
                },
                UNICODE_STRING,
                UNICODE_STRING,
            ],
        }
        self.assertEqual(res, decoded)

    def test_utf8_encode(self):
        """
        Test utf8 encoding.
        """
        # string value should be unchanged
        res = sg_jira.utils.unicode_to_utf8(UTF8_ENCODED_STRING)
        self.assertEqual(res, UTF8_ENCODED_STRING)

        # Utf-8 encoded string should be decoded
        res = sg_jira.utils.unicode_to_utf8(UNICODE_STRING)
        self.assertEqual(res, UTF8_ENCODED_STRING)

        # All values in a list should be decode if needed
        res = sg_jira.utils.unicode_to_utf8(
            [UTF8_ENCODED_STRING, UNICODE_STRING, UTF8_ENCODED_STRING]
        )
        self.assertEqual(
            res, [UTF8_ENCODED_STRING, UTF8_ENCODED_STRING, UTF8_ENCODED_STRING]
        )

        # All keys and values in a dict should be encoded if needed
        res = sg_jira.utils.unicode_to_utf8(
            {
                UNICODE_STRING: UNICODE_STRING,
                "foo": UTF8_ENCODED_STRING,
                "blah": 1,
                "%s_bis" % UNICODE_STRING: UTF8_ENCODED_STRING,
            }
        )
        self.assertEqual(
            res,
            {
                UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
                "foo": UTF8_ENCODED_STRING,
                "blah": 1,
                "%s_bis" % UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
            },
        )
        # Check that conflicts between a decoded key and an existing one are
        # correctly detected.
        with self.assertRaises(ValueError) as cm:
            # Note: we can't use self.assertRaisesRegexp which calls `str` on
            # the error message to perform the match, and fails with UnicodeEncodeError.
            sg_jira.utils.unicode_to_utf8(
                {
                    UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
                    "foo": UNICODE_STRING,
                    "blah": 1,
                    UNICODE_STRING: UTF8_ENCODED_STRING,
                }
            )
        self.assertIsNotNone(
            re.match(
                "UTF-8 encoded key for %s is already present in dictionary being encoded"
                % UNICODE_STRING,
                cm.exception.message,
            )
        )

        # A dictionary with lists
        res = sg_jira.utils.unicode_to_utf8(
            {
                UNICODE_STRING: UNICODE_STRING,
                "foo": [UTF8_ENCODED_STRING, UNICODE_STRING, UTF8_ENCODED_STRING],
                "blah": [1, 2, 3, 4],
                "%s_bis"
                % UTF8_ENCODED_STRING: [
                    UTF8_ENCODED_STRING,
                    UNICODE_STRING,
                    UTF8_ENCODED_STRING,
                ],
            }
        )
        self.assertEqual(
            res,
            {
                UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
                "foo": [UTF8_ENCODED_STRING, UTF8_ENCODED_STRING, UTF8_ENCODED_STRING],
                "blah": [1, 2, 3, 4],
                "%s_bis"
                % UTF8_ENCODED_STRING: [
                    UTF8_ENCODED_STRING,
                    UTF8_ENCODED_STRING,
                    UTF8_ENCODED_STRING,
                ],
            },
        )
        # A list of dictionaries
        d = {
            UNICODE_STRING: UNICODE_STRING,
            "foo": [UTF8_ENCODED_STRING, UNICODE_STRING, UTF8_ENCODED_STRING],
            "blah": [1, 2, 3, 4],
            "%s_bis"
            % UTF8_ENCODED_STRING: [
                UTF8_ENCODED_STRING,
                UNICODE_STRING,
                UTF8_ENCODED_STRING,
            ],
        }
        res = sg_jira.utils.unicode_to_utf8([d] * 7)
        encoded = {
            UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
            "foo": [UTF8_ENCODED_STRING, UTF8_ENCODED_STRING, UTF8_ENCODED_STRING],
            "blah": [1, 2, 3, 4],
            "%s_bis"
            % UTF8_ENCODED_STRING: [
                UTF8_ENCODED_STRING,
                UTF8_ENCODED_STRING,
                UTF8_ENCODED_STRING,
            ],
        }
        self.assertEqual(res, [encoded] * 7)
        # Nested dictionaries lists and tuples
        d = {
            UNICODE_STRING: UNICODE_STRING,
            "foo": (UTF8_ENCODED_STRING, UNICODE_STRING, UTF8_ENCODED_STRING),
            "blah": [1, 2, 3, 4],
            "%s_bis"
            % UTF8_ENCODED_STRING: [
                UNICODE_STRING,
                {
                    UNICODE_STRING: UNICODE_STRING,
                    "foo": [UTF8_ENCODED_STRING, UNICODE_STRING, UTF8_ENCODED_STRING],
                    "blah": [1, 2, 3, 4],
                    "%s_bis"
                    % UTF8_ENCODED_STRING: [
                        UTF8_ENCODED_STRING,
                        UNICODE_STRING,
                        UTF8_ENCODED_STRING,
                    ],
                },
                UNICODE_STRING,
                UTF8_ENCODED_STRING,
            ],
        }
        res = sg_jira.utils.unicode_to_utf8(d)
        encoded = {
            UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
            "foo": (UTF8_ENCODED_STRING, UTF8_ENCODED_STRING, UTF8_ENCODED_STRING),
            "blah": [1, 2, 3, 4],
            "%s_bis"
            % UTF8_ENCODED_STRING: [
                UTF8_ENCODED_STRING,
                {
                    UTF8_ENCODED_STRING: UTF8_ENCODED_STRING,
                    "foo": [
                        UTF8_ENCODED_STRING,
                        UTF8_ENCODED_STRING,
                        UTF8_ENCODED_STRING,
                    ],
                    "blah": [1, 2, 3, 4],
                    "%s_bis"
                    % UTF8_ENCODED_STRING: [
                        UTF8_ENCODED_STRING,
                        UTF8_ENCODED_STRING,
                        UTF8_ENCODED_STRING,
                    ],
                },
                UTF8_ENCODED_STRING,
                UTF8_ENCODED_STRING,
            ],
        }
        self.assertEqual(res, encoded)
