# -*- coding: utf-8 -*-

# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import json
import logging
import os
from io import BytesIO
from unittest import TestCase, mock

from jira import JIRAError
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

    Events sent to :meth:`sync_in_shotgun` are kept in ``synced_events``, and
    :attr:`jira` is a mock of the Jira session the automation requests are
    resolved with.
    """

    def __init__(self):
        """Initialize the mock server."""
        self.synced_events = []
        self._jira = mock.Mock()
        self._jira.issue.return_value.id = "10001"
        self._jira.issue.return_value.key = "KEY-1"
        self._jira.get_jira_issue_field_id.return_value = "customfield_sync"

    @property
    def sync_settings_names(self):
        return ["valid", UNICODE_STRING]

    def sync_in_jira(self, *args, **kwargs):
        return False

    def sync_in_shotgun(self, *args, **kwargs):
        self.synced_events.append(kwargs.get("event"))
        return True

    def admin_reset(self, *args, **kwargs):
        return True

    @property
    def jira(self):
        """The mock Jira session."""
        return self._jira


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
            f"Invalid request payload {payload}, unable to retrieve a Shotgun Entity type and its id".encode(
                "utf-8"
            )
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

    # -------------------------------------------------------------------------------
    # Jira to FPTR - Project Automation
    # -------------------------------------------------------------------------------

    def _post_automation(self, server, payload=None, path="/jira2sg/valid/issue/KEY-1"):
        """
        Send a Project Automation request to the web app and return its response.

        :param server: The mock server the request is handled with.
        :param dict payload: The body of the request, a full sync of an Issue by default.
        :param str path: The path of the request.
        :returns: The raw bytes of the response.
        """
        handler = webapp.RequestHandler(
            MockRequest(
                path,
                payload
                or {
                    "source": "jira_project_automation",
                    "actor": {"accountId": "user-1"},
                },
            ),
            ("localhost", -1),
            server,
        )
        return handler.wfile.getvalue()

    def test_jira_route_webhook_payload_untouched(
        self, mocked_finish, mocked_jira, mocked_sg
    ):
        """
        Check that a payload sent by a Jira site webhook is passed on as is.

        Expected result:
        - the syncer receives the very payload which was posted
        - Jira is not asked anything, as only automation requests are resolved
        """
        server = MockServer()
        payload = {"webhookEvent": "jira:issue_updated", "changelog": {"items": []}}

        raw_response = self._post_automation(server, payload)

        self.assertTrue(b"200 POST" in raw_response)
        self.assertEqual(server.synced_events, [payload])
        server.jira.issue.assert_not_called()

    def test_jira_route_automation_issue_payload_normalized(
        self, mocked_finish, mocked_jira, mocked_sg
    ):
        """
        Check that a Project Automation body reaches the syncer as a webhook event.

        Expected result:
        - the syncer receives an Issue update event, for the Issue of the path
        - the actor of the rule is the user of the event
        """
        server = MockServer()

        raw_response = self._post_automation(server)

        self.assertTrue(b"200 POST request successful" in raw_response)
        (event,) = server.synced_events
        self.assertEqual(event["webhookEvent"], "jira:issue_updated")
        self.assertEqual(event["issue"], {"key": "KEY-1", "id": "10001"})
        self.assertEqual(event["user"], {"accountId": "user-1"})

    def test_jira_route_automation_comment_payload_normalized(
        self, mocked_finish, mocked_jira, mocked_sg
    ):
        """
        Check that a comment rule is read back from Jira before it is synced.

        Expected result:
        - the comment is read for the Issue of the path and the id of the rule
        - the syncer receives the comment as Jira has it
        """
        server = MockServer()
        server.jira.comment_as_webhook_entity.return_value = {
            "id": "5001",
            "author": {"accountId": "human-1"},
        }

        raw_response = self._post_automation(
            server,
            {
                "source": "jira_project_automation",
                "actor": {"accountId": "user-1"},
                "event_type": "comment_created",
                "id": "5001",
            },
        )

        self.assertTrue(b"200 POST request successful" in raw_response)
        (event,) = server.synced_events
        self.assertEqual(event["webhookEvent"], "comment_created")
        self.assertEqual(event["comment"]["author"], {"accountId": "human-1"})
        server.jira.comment_as_webhook_entity.assert_called_once_with("KEY-1", "5001")

    def test_jira_route_automation_invalid_payload_rejected(
        self, mocked_finish, mocked_jira, mocked_sg
    ):
        """
        Check that a mistake in a rule is a bad request, with a message to fix it.

        Expected result:
        - a 400 whose message names the problem, shown in the Jira audit log
        - nothing is synced
        """
        server = MockServer()

        raw_response = self._post_automation(
            server, {"source": "jira_project_automation"}  # no actor
        )

        self.assertTrue(b"400 actor is required" in raw_response)
        self.assertEqual(server.synced_events, [])

    def test_jira_route_automation_resource_not_an_issue_rejected(
        self, mocked_finish, mocked_jira, mocked_sg
    ):
        """Check that an automation request can only be for an Issue resource."""
        server = MockServer()

        raw_response = self._post_automation(
            server, path="/jira2sg/valid/project/KEY-1"
        )

        self.assertTrue(
            b"400 Jira Project Automation only supports Issue" in raw_response
        )
        self.assertEqual(server.synced_events, [])

    def test_jira_route_automation_unknown_issue_rejected(
        self, mocked_finish, mocked_jira, mocked_sg
    ):
        """
        Check that an Issue which does not exist is a bad request.

        Expected result:
        - a 400 saying which Issue was not found
        - nothing is synced
        """
        server = MockServer()
        server.jira.issue.side_effect = JIRAError(status_code=404)

        raw_response = self._post_automation(server)

        self.assertTrue(b"400 Jira Issue 'KEY-1' was not found" in raw_response)
        self.assertEqual(server.synced_events, [])

    def test_jira_route_automation_jira_failure_is_bad_gateway(
        self, mocked_finish, mocked_jira, mocked_sg
    ):
        """
        Check that Jira failing is not reported as a mistake in the rule.

        Expected result:
        - a 502, so that nobody looks for a problem in the rule or the bridge
        - the status of Jira is in the message, the text of its error is not
        - nothing is synced
        """
        for status in (401, 403, 429, 500, 503):
            with self.subTest(status=status):
                server = MockServer()
                server.jira.issue.side_effect = JIRAError(
                    status_code=status, text="secret detail of the Jira error"
                )

                raw_response = self._post_automation(server)

                self.assertTrue(b"HTTP/1.1 502" in raw_response)
                self.assertIn(b"HTTP %d" % status, raw_response)
                self.assertNotIn(b"secret detail", raw_response)
                self.assertEqual(server.synced_events, [])

    def test_jira_route_automation_comment_read_failure_is_bad_gateway(
        self, mocked_finish, mocked_jira, mocked_sg
    ):
        """Check that Jira failing while reading a comment is a 502 as well."""
        server = MockServer()
        server.jira.comment_as_webhook_entity.side_effect = JIRAError(status_code=503)

        raw_response = self._post_automation(
            server,
            {
                "source": "jira_project_automation",
                "actor": {"accountId": "user-1"},
                "event_type": "comment_updated",
                "id": "5001",
            },
        )

        self.assertTrue(b"HTTP/1.1 502" in raw_response)
        self.assertEqual(server.synced_events, [])

    def test_jira_route_automation_id_wrong_type_rejected(
        self, mocked_finish, mocked_jira, mocked_sg
    ):
        """
        Check that an id which is neither a string nor an integer is a bad request.

        Expected result:
        - a 400, and not a 500
        - nothing is synced
        """
        server = MockServer()

        raw_response = self._post_automation(
            server,
            {
                "source": "jira_project_automation",
                "actor": {"accountId": "user-1"},
                "event_type": "comment_created",
                "id": ["1"],
            },
        )

        self.assertTrue(b"HTTP/1.1 400" in raw_response)
        self.assertEqual(server.synced_events, [])

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


class TestMain(TestCase):
    """The command line of the web app."""

    def _run_main(self, *args):
        """
        Run ``webapp.main()`` with the given arguments, without serving anything.

        :returns: The mock which stands for ``webapp.run_server``.
        """
        with mock.patch("sys.argv", ["webapp.py", *args]), mock.patch(
            "webapp.run_server"
        ) as run_server:
            webapp.main()
        return run_server

    def test_main_settings_file_passed_to_the_server(self):
        """
        Check that the settings file of the command line is the one which is used.

        Expected result:
        - the server is run with that file, and in HTTP mode
        """
        run_server = self._run_main("--settings", "/some/settings.py")

        run_server.assert_called_once_with(
            listen_address="127.0.0.1",
            port=9090,
            settings="/some/settings.py",
            keyfile=None,
            certfile=None,
        )

    def test_main_ssl_context_enables_https(self):
        """Check that a key and a certificate file run the server in HTTPS mode."""
        run_server = self._run_main(
            "--settings", "s.py", "--ssl_context", "key.pem", "cert.pem"
        )

        kwargs = run_server.call_args.kwargs
        self.assertEqual(kwargs["keyfile"], "key.pem")
        self.assertEqual(kwargs["certfile"], "cert.pem")

    def test_main_settings_required(self):
        """Check that the web app does not start without a settings file."""
        with mock.patch("webapp.run_server") as run_server, self.assertRaises(
            SystemExit
        ):
            self._run_main()

        run_server.assert_not_called()

    def test_main_invalid_listen_address_rejected(self):
        """Check that an address which is not an IPv4 one is refused."""
        with self.assertRaises(SystemExit):
            self._run_main("--settings", "s.py", "--listen_address", "not-an-ip")
