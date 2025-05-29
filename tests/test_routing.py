# -*- coding: utf-8 -*-

# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import json
import mock
import logging

from io import BytesIO
from test_base import TestBase
import webapp

# Raw POST request template
POST_TEMPLATE = """POST {path} HTTP/1.1
Host: httpbin.org
Connection: keep-alive
Accept: */*
User-Agent: Mozilla/4.0 (compatible; esp8266 Lua; Windows NT 5.1)
Content-Type: application/json
Content-Length: {content_length}

{payload}
"""

UNICODE_STRING = "unicode_îéö_😀"


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

    def admin_reset(self, *args, **kwargs):
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
                return BytesIO(f"GET {self._path} HTTP/1.1".encode("utf-8"))
            else:
                payload = json.dumps(self._payload)
                post_template = POST_TEMPLATE.format(
                    path=self._path, content_length=len(payload), payload=payload
                )
                return BytesIO(post_template.encode("utf-8"))
        elif mode == "wb":
            # Response, return a writable empty file like object
            return BytesIO(b"")


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
        super().setUp()
        # This is controlled by the bridge settings that we don't
        # load in these tests.
        # Our custom MockRequest using StringIO causes problems when running
        # tests with xmlrunner, so, as a workaround, we set the logging level
        # to warning to avoid unicode problems, depending on the order the tests
        # are run.
        logging.getLogger("webapp").setLevel(logging.WARNING)
        self.set_sg_mock_schema(os.path.join(self._fixtures_path, "schemas", "sg-jira"))

    def test_bad_routes(self, mocked_finish, mocked_jira, mocked_sg):
        """
        Test all bad routes fail

        Requests with no payload are GET requests.
        Requests with a payload are POST requests.
        """
        server = MockServer()

        # GET request with an invalid action
        handler = webapp.RequestHandler(
            MockRequest("/badaction", None), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"400 Invalid request path /badaction" in raw_response)
        # GET request with an invalid action but valid settings name
        handler = webapp.RequestHandler(
            MockRequest("/badaction/valid", None), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"400 Invalid request path /badaction/valid" in raw_response)
        # POST request with an invalid action
        handler = webapp.RequestHandler(
            MockRequest("/badaction", {"foo": "blah"}), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"400 Invalid request path /badaction" in raw_response)
        # POST request with an invalid action but valid settings name
        handler = webapp.RequestHandler(
            MockRequest("/badaction/valid", {"foo": "blah"}), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"400 Invalid request path /badaction/valid" in raw_response)

    def test_sg_route(self, mocked_finish, mocked_jira, mocked_sg):
        """
        Test routing from PTR to Jira

        Requests with no payload are GET requests.
        Requests with a payload are POST requests.
        """
        server = MockServer()
        # GET request with an invalid settings name
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/badsettings", None), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"400 Invalid settings name badsettings" in raw_response)
        # GET request with a valid settings name
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/valid", None), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"HTTP/1.1 200" in raw_response)
        self.assertTrue(b"<p>Syncing with valid settings.</p>" in raw_response)
        # POST request with invalid payload missing entity information
        payload = {"foo": "blah"}
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/valid", payload), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(
            f"Invalid request payload {payload}, unable to retrieve a Shotgun Entity type and its id".encode("utf-8")
            in raw_response
        )

        # POST request with invalid entity info in path
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/valid/Task/notanumber", {"foo": "blah"}),
            ("localhost", -1),
            server,
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(
            b"Invalid Shotgun Task id notanumber, it must be a number." in raw_response
        )

        # POST request with invalid path: missing entity_id
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/valid/Task", {"foo": "blah"}),
            ("localhost", -1),
            server,
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"Invalid request path /sg2jira/valid/Task" in raw_response)
        # POST request with invalid settings name - Task in path
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/badsettings/Task/123", {"foo": "blah"}),
            ("localhost", -1),
            server,
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"Invalid settings name badsettings" in raw_response)

        # Invalid Task Payload missing entity_id
        invalid_payload = {"entity_type": "Task"}
        # POST request with invalid payload missing entity_type
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/valid", invalid_payload), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"Invalid request payload" in raw_response)

        # Invalid Task Payload missing entity_type
        invalid_payload = {"entity_id": 123}
        # POST request with invalid payload missing entity_type
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/valid", invalid_payload), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"Invalid request payload" in raw_response)

        # Valid Task Payload
        valid_payload = {
            "entity_type": "Task",
            "entity_id": 999,
        }
        # POST request with invalid settings name - Task in payload
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/badsettings", valid_payload),
            ("localhost", -1),
            server,
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"Invalid settings name badsettings" in raw_response)

        # POST request with valid payload
        handler = webapp.RequestHandler(
            MockRequest("/sg2jira/valid", valid_payload), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"200 POST request successful" in raw_response)

    def test_jira_route(self, mocked_finish, mocked_jira, mocked_sg):
        """
        Test routing from Jira to PTR

        Requests with no payload are GET requests.
        Requests with a payload are POST requests.
        """
        server = MockServer()
        # GET request with an invalid settings name
        handler = webapp.RequestHandler(
            MockRequest("/jira2sg/badsettings", None), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"400 Invalid settings name badsettings" in raw_response)
        # GET request with a valid settings name
        handler = webapp.RequestHandler(
            MockRequest("/jira2sg/valid", None), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"HTTP/1.1 200" in raw_response)
        self.assertTrue(b"<p>Syncing with valid settings.</p>" in raw_response)
        # POST request with invalid path: missing resource type and key
        handler = webapp.RequestHandler(
            MockRequest("/jira2sg/valid", {"foo": "blah"}), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(
            b"Invalid request path /jira2sg/valid, it must include a Jira resource type and its key"
            in raw_response
        )

        # POST request with invalid path: missing resource key
        handler = webapp.RequestHandler(
            MockRequest("/jira2sg/valid/issue", {"foo": "blah"}),
            ("localhost", -1),
            server,
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"Invalid request path /jira2sg/valid/issue" in raw_response)
        # POST request with invalid settings name
        handler = webapp.RequestHandler(
            MockRequest("/jira2sg/badsettings/issue/BLAH", {"foo": "blah"}),
            ("localhost", -1),
            server,
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"Invalid settings name badsettings" in raw_response)

        # POST request with valid path
        handler = webapp.RequestHandler(
            MockRequest("/jira2sg/valid/issue/BLAH", {"foo": "blah"}),
            ("localhost", -1),
            server,
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"200 POST request successful" in raw_response)

    def test_admin_route(self, mocked_finish, mocked_jira, mocked_sg):
        """
        Test routing to Admin

        Requests with no payload are GET requests.
        Requests with a payload are POST requests.
        """
        server = MockServer()

        # GET admin requests are not supported, ensure they fail as expected

        # GET admin action with a valid settings name instead of action
        handler = webapp.RequestHandler(
            MockRequest("/admin/valid", None), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"400 Invalid request path /admin/valid" in raw_response)
        # GET valid admin action path should fail with GET
        handler = webapp.RequestHandler(
            MockRequest("/admin/reset", None), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"HTTP/1.1 400" in raw_response)
        self.assertTrue(b"400 Invalid request path /admin/reset" in raw_response)
        # POST request with invalid admin action
        handler = webapp.RequestHandler(
            MockRequest("/admin/badaction", {"foo": "bar"}), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"Invalid admin path '/admin/badaction'" in raw_response)

        # POST request with a valid admin action should succeed.
        handler = webapp.RequestHandler(
            MockRequest("/admin/reset", {"foo": "bar"}), ("localhost", -1), server
        )
        raw_response = handler.wfile.getvalue()
        self.assertTrue(b"200 POST request successful" in raw_response)
