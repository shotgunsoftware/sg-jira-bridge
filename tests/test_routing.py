# -*- coding: utf-8 -*-

# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import StringIO
import json
import mock
import logging

from test_base import TestBase
import webapp

# Raw POST request template
POST_TEMPLATE = """POST %s HTTP/1.1
Host: httpbin.org
Connection: keep-alive
Accept: */*
User-Agent: Mozilla/4.0 (compatible; esp8266 Lua; Windows NT 5.1)
Content-Type: application/json
Content-Length: %d

%s
"""

UNICODE_STRING = u"unicode_îéö_😀"
UTF8_ENCODED_STRING = UNICODE_STRING.encode("utf-8")


class MockServer(object):
    """
    Mock some of the web server methods.
    """
    @property
    def sync_settings_names(self):
        return ["valid", UNICODE_STRING]

    def sync_in_jira(self, *args, **kwargs):
        return False

    def sync_in_shotgun(self, *args, **kwargs):
        return True


class MockRequest(object):
    """
    Mock making requests at the socket level.
    """
    def __init__(self, path, payload):
        self._path = path
        self._payload = payload

    def makefile(self, mode, *args, **kwargs):
        """
        Use a file like object to mock the socket read/write.
        """
        if mode == "rb":
            # Incoming request, issue a GET if we don't have any payload,
            # otherwise assume a POST.
            if not self._payload:
                return StringIO.StringIO("GET %s HTTP/1.1" % self._path)
            else:
                payload = json.dumps(self._payload)
                return StringIO.StringIO(
                    POST_TEMPLATE % (
                        self._path,
                        len(payload),
                        payload
                    )
                )
        elif mode == "wb":
            # Response, return a writable empty file like object
            return StringIO.StringIO("")


def faked_finish(*args, **kwargs):
    """
    Empty method to prevent the request handler to close its rfile and wfile so
    we can read the result after a request has been processed.
    """
    pass


# Mock Shotgun with mockgun, this works only if the code uses shotgun_api3.Shotgun
# and does not work if using `from shotgun_api3 import Shotgun` and 
# then `sg = Shotgun(...)`
@mock.patch("shotgun_api3.Shotgun")
# Mock Jira with MockedJira, this works only if the code uses jira.client.JIRA
# and does not `from jira import JIRA` and then `jira_handle = JIRA(...)`
@mock.patch("jira.client.JIRA")
@mock.patch("webapp.RequestHandler.finish", side_effect=faked_finish)
class TestRouting(TestBase):
    """
    Test url dispatch through the webapp
    """
    def setUp(self):
        super(TestRouting, self).setUp()
        # This is controlled by the bridge settings that we don't
        # load in these tests.
        # Our custom MockRequest using StringIO causes problems when running
        # tests with xmlrunner, so, as a workaround, we set the logging level
        # to warning to avoid unicode problems, depending on the order the tests
        # are run.
        logging.getLogger("webapp").setLevel(logging.WARNING)
        self.set_sg_mock_schema(
            os.path.join(self._fixtures_path, "schemas", "sg-jira")
        )

    def test_sg_route(self, mocked_finish, mocked_jira, mocked_sg):
        """
        Test routing from SG to Jira
        """
        server = MockServer()
        # GET request with an invalid settings name
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/default", None),
            ("localhost", -1),
            server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue("400 Invalid settings name default" in raw_response)
        # GET request with a valid settings name
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/valid", None),
            ("localhost", -1),
            server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue("HTTP/1.1 200" in raw_response)
        self.assertTrue("<p>Syncing with valid settings.</p>" in raw_response)
        # POST request with invalid payload
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/valid", {"foo": "blah"}),
            ("localhost", -1),
            server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(
            "Invalid request payload {u'foo': u'blah'}, unable to retrieve a "
            "Shotgun Entity type and its id" in raw_response
        )
        payload = {
            "entity_type": "Task",
            "entity_id": "999",
        }
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/valid", payload),
            ("localhost", -1),
            server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue("200 POST request successful" in raw_response)

    def test_jira_route(self, mocked_finish, mocked_jira, mocked_sg):
        """
        Test routing from Jira to SG
        """
        server = MockServer()
        # GET request with an invalid settings name
        handler = webapp.RequestHandler(
            MockRequest("/jira2sg/default", None),
            ("localhost", -1),
            server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue("400 Invalid settings name default" in raw_response)
        # GET request with a valid settings name
        handler = webapp.RequestHandler(
            MockRequest("/jira2sg/valid", None),
            ("localhost", -1),
            server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue("HTTP/1.1 200" in raw_response)
        self.assertTrue("<p>Syncing with valid settings.</p>" in raw_response)
        # POST request with invalid path: a resource type and key must be provided
        handler = webapp.RequestHandler(
            MockRequest("/jira2sg/valid", {"foo": "blah"}),
            ("localhost", -1),
            server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(
            "Invalid request path /jira2sg/valid, it must include a Jira "
            "resource type and its key" in raw_response
        )
        handler = webapp.RequestHandler(
            MockRequest("/jira2sg/valid/issue/BLAH", {"foo": "blah"}),
            ("localhost", -1),
            server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue("200 POST request successful" in raw_response)

    def test_unicode(self, mocked_finish, mocked_jira, mocked_sg):
        """
        Test unicode values are correclty handled.
        """
        server = MockServer()
        # GET request with settings name unicode characters.
        unicode_url = "/jira2sg/%s" % UNICODE_STRING
        handler = webapp.RequestHandler(
            MockRequest(unicode_url, None),
            ("localhost", -1),
            server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue("HTTP/1.1 200" in raw_response)
        self.assertTrue(
            ("<p>Syncing with %s settings.</p>" % UNICODE_STRING) in raw_response
        )
        handler = webapp.RequestHandler(
            MockRequest("%s/issue/%s" % (unicode_url, UNICODE_STRING), {"foo": UNICODE_STRING, UNICODE_STRING: UNICODE_STRING}),
            ("localhost", -1),
            server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue("200 POST request successful" in raw_response)
