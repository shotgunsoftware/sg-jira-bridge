# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import argparse
import json
import logging
import re
import socket
import ssl
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib import parse

import sg_jira

DESCRIPTION = """
A simple web app frontend to the PTR Jira bridge.
"""

CSS_TEMPLATE = """
        <style>
            body {
                margin: 0;
                background-color: #eee;
                font-family: Arial, Helvetica, sans-serif;
            }
            h1 {
                background-color: whitesmoke;
                color: #00BAFF;
                border-radius: 5px;
                padding: 5 5 5 15px;
                border-bottom: 1px solid #ddd;
            }
            .content { margin: 0 0 15px 15px; }
            .error { margin: 0 0 15px 15px; }
            .details { margin: 40px 0 15px 15px; }
            h2 { margin-bottom: 10px; }
            p { margin-top: 10px; }
        </style>
"""

HMTL_TEMPLATE = """
    <head>
        <title>PTR Jira Bridge: %s</title>
        {style}
    </head>
    <body>
        <h1>PTR Jira Bridge</h1>
        <div class="content">
            <h2>%s</h2>
            <p>%s</p>
        </div>
    </body>
</html>
""".format(
    style=CSS_TEMPLATE
)

# We overriding the default html error template to render errors to the user.
# This template *requires* the following format tokens:
# - %(code)d - for the response code
# - %(explain)s - for the short explanation of the response code
# - %(message)s - for a detailed message about the error
HTML_ERROR_TEMPLATE = """
    <head>
        <title>PTR Jira Bridge Error %(code)d: %(message)s</title>
        {style}
    </head>
    <body>
        <h1>PTR Jira Bridge</h1>
        <div class="error">
            <h2>Error %(code)d</h2>
            <p>%(explain)s</p>
        </div>
        <div class="details">
            <p><strong>Details: </strong> <pre>%(message)s</pre></p>
        </div>
    </body>
""".format(
    style=CSS_TEMPLATE
)

# Please note that we can't use __name__ here as it would be __main__
logger = logging.getLogger("webapp")


def get_sg_jira_bridge_version():
    """
    Helper to extract a version number for the sg-jira-bridge module.

    This will attenmpt to extract the version number from git if installed from
    a cloned repo. If a version is unable to be determined, or the process
    fails for any reason, we return "dev"

    :returns: A major.minor.patch[.sub] version string or "dev".
    """
    # Note: if you install from a cloned git repository
    # (e.g. pip install ./tk-core), the version number
    # will be picked up from the most recently added tag.
    try:
        version_git = subprocess.check_output(
            ["git", "describe", "--abbrev=0"]
        ).rstrip()
        return version_git
    except Exception:
        # Blindly ignore problems. Git might be not available, or the user may
        # have installed via a zip archive, etc...
        pass

    return "dev"


class SgJiraBridgeBadRequestError(Exception):
    """
    Custom exception so we can differentiate between errors we raise that
    should return 4xx error codes and errors in the application which should
    return 500 error codes.
    """

    pass


class Server(ThreadingMixIn, HTTPServer):
    """
    Basic server with threading functionality mixed in. This will help the server
    keep up with a high volume of throughput from Flow Production Tracking and Jira.
    """

    def __init__(self, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sg_jira = sg_jira.Bridge.get_bridge(settings)

    def sync_in_jira(self, *args, **kwargs):
        """
        Just pass the given parameters to the PTR Jira Brige method.
        """
        return self._sg_jira.sync_in_jira(*args, **kwargs)

    def sync_in_shotgun(self, *args, **kwargs):
        """
        Just pass the given parameters to the PTR Jira Brige method.
        """
        return self._sg_jira.sync_in_shotgun(*args, **kwargs)

    def admin_reset(self, *args, **kwargs):
        """
        Just pass the given parameters to the PTR Jira Bridge method.
        """
        return self._sg_jira.reset(*args, **kwargs)

    @property
    def sync_settings_names(self):
        """
        Return the list of sync settings this server handles.
        """
        return self._sg_jira.sync_settings_names


class RequestHandler(BaseHTTPRequestHandler):
    # On Python3, in socketserver.StreamRequestHandler, if this is
    # set it will use makefile() to produce the output stream. Otherwise,
    # it will use socketserver._SocketWriter, and we won't be able to get
    # to the data.
    # taken from https://stackoverflow.com/a/53163148/4223964
    wbufsize = 1

    protocol_version = "HTTP/1.1"
    # Inject the version of sg-jira-bridge into server_version for the headers.
    server_version = "sg-jira-bridge/%s %s" % (
        get_sg_jira_bridge_version(),
        BaseHTTPRequestHandler.server_version,
    )
    # BaseHTTPServer Class variable that stores the HTML template for error
    # pages. Override the default error page template with our own.
    error_message_format = HTML_ERROR_TEMPLATE

    def post_response(self, response_code, message, content=None):
        """
        Convenience method for handling the response

        Handles sending the response, setting headers, and writing any
        content in the expected order. Sets appropriate headers including
        content length which is required by HTTP/1.1.

        :param int response_code: Standard HTTP response code sent in headers.
        :param str message: Message to accompany response code in headers.
        :param str content: Optional content to return as content in the
            response. This is typically html displayed in a browser.
        """
        # NOTE: All responses must:
        #   - send the response first.
        #   - then, if there is some data, call end_headers to add a blank line.
        #   - then write the data, if any, with self.wfile.write
        self.send_response(response_code, message)

        content_len = 0
        if content:
            content_len = len(content)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", content_len)
        # TODO: Ideally we use the default functionality of HTTP/1.1 where
        # keep-alive is True (no header needed). However, for some reason,
        # this currently blocks new connections for 60 seconds (likely the
        # default keep-alive timeout). So for now we explicitly close the
        # connection with the header below to ensure things run smoothly.
        # Once the issue has been resolved, we can remove this header.
        self.send_header("Connection", "close")
        self.end_headers()
        if content:
            self.wfile.write(content)

    def do_GET(self):
        """
        Handle a GET request.
        """
        # Extract path components from the path, ignore leading '/' and
        # discard empty values coming from '/' at the end or multiple
        # contiguous '/'.
        path_parts = [x for x in self.path[1:].split("/") if x]
        if not path_parts:
            self.post_response(
                200,
                "The server is alive",
                HMTL_TEMPLATE % ("The server is alive", "The server is alive", ""),
            )
            return

        # Return a correct error for browser favicon requests in order to
        # reduce confusing log messages that look bad but aren't.
        if len(path_parts) == 1 and path_parts[0] == "favicon.ico":
            self.send_error(404)
            return

        if path_parts[0] == "sg2jira":
            title = "Shotgun to Jira"
        elif path_parts[0] == "jira2sg":
            title = "Jira to Shotgun"
        else:
            self.send_error(400, "Invalid request path %s" % self.path)
            return

        settings_name = path_parts[1]
        if str(settings_name) not in self.server.sync_settings_names:
            self.send_error(400, "Invalid settings name %s" % settings_name)
            return

        # Success, send a basic html page.
        self.post_response(
            200,
            f"Syncing with {settings_name} settings.".encode(),
            (
                HMTL_TEMPLATE
                % (title, title, f"Syncing with {settings_name} settings.")
            ).encode(),
        )

    def do_POST(self):
        """
        Handle a POST request.

        Post url paths need to have the form::

          sg2jira/<settings_name>[/<sg_entity_type>/<sg_entity_id>]
          jira2sg/<settings_name>/<jira_resource_type>/<jira_resource_key>
          admin/reset

        If the PTR Entity is not specified in the path, it must be specified in
        the provided payload.
        """
        # /sg2jira/default[/Task/123]
        # /jira2sg/default/Issue/KEY-123
        # /admin/reset
        try:
            parsed = parse.urlparse(self.path)
            # Extract additional query parameters.
            # What they could be is still TBD, may be things like `dry_run=1`?
            parameters = {}
            if parsed.query:
                parameters = parse.parse_qs(parsed.query, True, True)

            # Extract path components from the path, ignore leading '/' and
            # discard empty values coming from '/' at the end or multiple
            # contiguous '/'.
            path_parts = [x for x in parsed.path[1:].split("/") if x]

            if not path_parts:
                self.send_error(400, "Invalid request path %s" % self.path)
            # Treat the command
            if path_parts[0] == "admin":
                self._handle_admin_request(path_parts, parameters)
            elif path_parts[0] in ["sg2jira", "jira2sg"]:
                self._handle_sync_request(path_parts, parameters)
            else:
                self.send_error(
                    400,
                    "Invalid request path %s: unknown command %s"
                    % (self.path, path_parts[0]),
                )
                return

            self.post_response(200, "POST request successful")

        except SgJiraBridgeBadRequestError as e:
            self.send_error(400, str(e))
        except Exception as e:
            self.send_error(500, str(e))
            logger.debug(e, exc_info=True)

    def _read_payload(self):
        """
        Read the body of a request to get the payload.

        :returns: payload as a dictionary or empty dict if there was no payload
        """
        content_type = self.headers.get("content-type")
        # Check the content type, if not set we assume json.
        # We can have a charset just after the content type, e.g.
        # application/json; charset=UTF-8.

        if content_type and not re.search(r"\s*application/json\s*;?", content_type):
            raise SgJiraBridgeBadRequestError(
                "Invalid content-type %s, it must be 'application/json'" % content_type
            )

        content_len = int(self.headers.get("content-length", 0))
        body = self.rfile.read(content_len)
        payload = {}
        if body:
            payload = json.loads(body)

        return payload

    def _handle_sync_request(self, path_parts, parameters):
        """
        Handle a request to sync between Flow Production Tracking and Jira in either direction.

        At this point, only the action (the first path_part) from the request
        path has been validated. The rest of the path_parts still need to be
        validated before we proceed. We expect the path to for this request to
        be one of the following:

            sg2jira/<settings_name>[/<sg_entity_type>/<sg_entity_id>]
            jira2sg/<settings_name>/<jira_resource_type>/<jira_resource_key>

        If the PTR Entity is not specified in the path, it must be present in
        the loaded payload.

        :param list path_parts: List of strings representing each part of the
            URL path that this request accessed. For example,
            ``["sg2jira", "default", "Task", "123"]``.
        :param dict parameters: Optional additional parameters that were extracted
            from the url.
        :raises SgJiraBridgeBadRequestError: If there is any problem we detect with the
            path, or payload.
        """
        entity_type = None
        entity_key = None
        if len(path_parts) == 4:
            direction, settings_name, entity_type, entity_key = path_parts
        elif len(path_parts) == 2:
            direction, settings_name = path_parts
        else:
            raise SgJiraBridgeBadRequestError("Invalid request path %s" % self.path)

        if str(settings_name) not in self.server.sync_settings_names:
            raise SgJiraBridgeBadRequestError(
                "Invalid settings name %s" % settings_name
            )

        payload = self._read_payload()

        if direction == "sg2jira":
            # Ensure we get a valid entity_type and entity_id
            if not entity_type or not entity_key:
                # We need to retrieve this from the payload.
                entity_type = payload.get("entity_type")
                entity_key = payload.get("entity_id")
            if not entity_type or not entity_key:
                raise SgJiraBridgeBadRequestError(
                    "Invalid request payload %s, unable to retrieve a Shotgun Entity type and its id."
                    % payload
                )
            # We could have a str or int here depending on how it was sent.
            try:
                entity_key = int(entity_key)
            except ValueError as e:
                # log the original exception before we obfuscate it
                logger.debug(e, exc_info=True)
                raise SgJiraBridgeBadRequestError(
                    "Invalid Shotgun %s id %s, it must be a number."
                    % (
                        entity_type,
                        entity_key,
                    )
                )

            self.server.sync_in_jira(
                settings_name, entity_type, int(entity_key), event=payload, **parameters
            )

        elif direction == "jira2sg":
            if not entity_type or not entity_key:
                # We can't retrieve this easily from the webhook payload without
                # hard coding a list of supported resource types, so we require
                # it to be specified in the path for the time being.
                raise SgJiraBridgeBadRequestError(
                    "Invalid request path %s, it must include a Jira resource "
                    "type and its key" % self.path
                )

            self.server.sync_in_shotgun(
                settings_name, entity_type, entity_key, event=payload, **parameters
            )

    def _handle_admin_request(self, path_parts, parameters):
        """
        Handle admin request to the server.

        Currently handles a single action, ``reset`` which resets the Bridge
        in order to clear out the Flow Production Tracking schema cache.

        At this point, only the action (the first path_part) from the request
        path has been validated. The rest of the path_parts still need to be
        validated before we proceed.

            admin/reset

        :param list path_parts: List of strings representing each part of the
            URL path that this request accessed. For example,
            ``["admin", "reset"]``.
        :param dict parameters: Optional additional parameters that were extracted
            from the url.
        :raises SgJiraBridgeBadRequestError: If there is any problem we detect with the
            path, or payload.
        """
        # The only function we respond to now is reset
        if len(path_parts) != 2 or path_parts[1] != "reset":
            raise SgJiraBridgeBadRequestError(
                "Invalid admin path '%s'. Action is not set or unsupported." % self.path
            )

        self.server.admin_reset(**parameters)

    def log_message(self, format, *args):
        """
        Override :class:`BaseHTTPRequestHandler` method to use a
        standard logger.

        :param str format: A format string, e.g. '%s %s'.
        :param args: Arbitrary list of arguments to use with the format string.
        """
        message = "%s - %s - %s" % (self.client_address[0], self.path, format % args)
        logger.info(message)

    def log_error(self, format, *args):
        """
        Override :class:`BaseHTTPRequestHandler` method to use a
        standard logger.

        :param str format: A format string, e.g. '%s %s'.
        :param args: Arbitrary list of arguments to use with the format string.
        """
        message = "%s - %s - %s" % (self.client_address[0], self.path, format % args)
        logger.error(message)


def create_server(port, listen_address, settings, keyfile=None, certfile=None):
    """
    Create the server.

    :param int port: A port number to listen to.
    :param str listen_address: The address to listen to.
    :param str settings: Path to settings file.
    :param str keyfile: Optional path to a PEM key file to run in HTTPS mode.
    :param str certfile:  Optional path to a PEM certificate file to run in HTTPS mode.

    :returns: The HTTP Server
    :type: :class:`BaseHTTPRequestHandler`
    """
    httpd = Server(settings, (listen_address, port), RequestHandler)
    if keyfile and certfile:
        # Activate HTTPS.
        httpd.socket = ssl.wrap_socket(
            httpd.socket, keyfile=keyfile, certfile=certfile, server_side=True
        )
    return httpd


def run_server(port, listen_address, settings, keyfile=None, certfile=None):
    """
    Run the server until a shutdown is requested.

    :param int port: A port number to listen to.
    :param str listen_address: The address to listen to.
    :param str settings: Path to settings file.
    :param str keyfile: Optional path to a PEM key file to run in https mode.
    :param str certfile:  Optional path to a PEM certificate file to run in https mode.
    """
    create_server(port, listen_address, settings, keyfile, certfile).serve_forever()


def main():
    """
    Retrieve command line arguments and start the server.
    """
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "--listen_address",
        default="127.0.0.1",
        help="The IPv4 address that the server binds to. Use 0.0.0.0 to bind on all network interfaces.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9090,
        help="The port number to listen to.",
    )
    parser.add_argument("--settings", help="Full path to settings file.", required=True)
    parser.add_argument(
        "--ssl_context",
        help="A key and certificate file pair to run the server in HTTPS mode.",
        nargs=2,
    )

    args = parser.parse_args()

    keyfile = None
    certfile = None
    if args.ssl_context:
        keyfile, certfile = args.ssl_context

    try:
        socket.inet_aton(args.listen_address)
    except socket.error:
        print("The specified listen address is not a valid IPv4 address.")
        sys.exit(1)

    run_server(
        listen_address=args.listen_address,
        port=args.port,
        settings=args.settings,
        keyfile=keyfile,
        certfile=certfile,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Shutting down...")
