# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import re
import urlparse
import BaseHTTPServer
import json
import ssl
import logging
import sys

import sg_jira

HMTL_TEMPLATE = """
<html>
    <head>
        <title>%s</title>
        <style>
            body {background-color: #525252;}
            h1   {
                background-color: #2C93E2;
                color: whitesmoke;
                text-align: center;
                border-radius: 5px;
            }
            p    {color: whitesmoke; text-align: center;}
        </style>
    </head>
    <body >
        <h1>%s</h1>
        <p>%s</p>
    </body>
</html>
"""

# Please note that we can't use __name__ here as it would be __main__
logger = logging.getLogger("webapp")


class Server(BaseHTTPServer.HTTPServer):
    """
    A web server
    """
    def __init__(self, settings, *args, **kwargs):
        # Note: BaseHTTPServer.HTTPServer is not a new style class so we can't use
        # super here
        BaseHTTPServer.HTTPServer.__init__(self, *args, **kwargs)
        self._sg_jira = sg_jira.Bridge.get_bridge(settings)

    def sync_in_jira(self, *args, **kwargs):
        """
        Just pass the given parameters to the SG Jira Brige method.
        """
        return self._sg_jira.sync_in_jira(*args, **kwargs)

    def sync_in_shotgun(self, *args, **kwargs):
        """
        Just pass the given parameters to the SG Jira Brige method.
        """
        return self._sg_jira.sync_in_shotgun(*args, **kwargs)

    @property
    def sync_settings_names(self):
        """
        Return the list of sync settings this server handles.
        """
        return self._sg_jira.sync_settings_names


class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    request_version = "HTTP/1.0"  # TODO: support HTTP/1.1

    def do_GET(self):
        """
        Handle a GET request.
        """
        # Note: all responses must
        # - send the response or error code first.
        # - then, if there is some data, call end_headers to add a blank line.
        # - then write the data, if any, with self.wfile.write

        # Extract path components from the path, ignore leading '/' and
        # discard empty values coming from '/' at the end or multiple
        # contiguous '/'
        path_parts = [x for x in self.path[1:].split("/") if x]
        if not path_parts:
            self.send_response(200, "The server is alive")
            self.end_headers()
            self.wfile.write(
                HMTL_TEMPLATE % (
                    "The server is alive",
                    "The server is alive",
                    ""
                )
            )
            return
        if len(path_parts) < 2:
            self.send_error(400, "Invalid request path %s" % self.path)
            return
        if path_parts[0] == "sg2jira":
            title = "Shotgun to Jira"
        elif path_parts[0] == "jira2sg":
            title = "Jira to Shotgun"
        else:
            self.send_error(400, "Invalid action %s" % path_parts[0])
            return
        settings_name = path_parts[1]
        if settings_name not in self.server.sync_settings_names:
            self.send_error(400, "Invalid settings name %s" % settings_name)
            return
        # Success, send a basic html page
        self.send_response(200, "Syncing with %s settings." % settings_name)
        self.end_headers()
        self.wfile.write(
            HMTL_TEMPLATE % (
                title,
                title,
                "Syncing with %s settings." % settings_name
            )
        )

    def do_POST(self):
        """
        Handle a POST request.

        Post url paths need to have the forms:
          sg2jira/Settings name[/SG Entity type/SG Entity id]
          jira2sg/Settings name/Jira Resource type/Jira Resource key

        If the SG Entity is not specified in the path, it must be specified in
        the provided payload.
        """
        try:
            direction = None
            settings_name = None
            entity_type = None
            entity_key = None
            parsed = urlparse.urlparse(self.path)
            # Extract path components from the path, ignore leading '/' and
            # discard empty values coming from '/' at the end or multiple
            # contiguous '/'
            path_parts = [x for x in parsed.path[1:].split("/") if x]
            if len(path_parts) == 4:
                direction, settings_name, entity_type, entity_key = path_parts
            elif len(path_parts) == 2:
                direction, settings_name = path_parts
            else:
                self.send_error(400, "Invalid request path %s" % self.path)
                return
            # Extract additional query parameters
            # what they could be is still TBD, may be things like `dry_run=1`?
            parameters = {}
            if parsed.query:
                parameters = urlparse.parse_qs(parsed.query, True, True)
            # Read the body to get the payload
            content_type = self.headers.getheader("content-type")
            # Check the content type, if not set we assume json.
            # We can have a charset just after the content type, e.g.
            # application/json; charset=UTF-8
            if content_type and not re.search(r"\s*application/json\s*;?", content_type):
                self.send_error(
                    400,
                    "Invalid content %s, it must be 'application/json'" % content_type
                )
                return
            content_len = int(self.headers.getheader("content-length", 0))
            body = self.rfile.read(content_len)
            payload = {}
            if body:
                payload = json.loads(body)

            # Basic routing: extract the synch direction and additional values
            # from the path
            if direction == "sg2jira":
                if not entity_type or not entity_key:
                    # We need to retrieve this from the payload
                    entity_type = payload.get("entity_type")
                    entity_key = payload.get("entity_id")
                if not entity_type or not entity_key:
                    self.send_error(
                        400,
                        "Invalid request payload %s, unable to retrieve "
                        "a Shotgun Entity type and its id." % (payload)
                    )
                    return
                if not entity_key.isdigit():
                    self.send_error(
                        400,
                        "Invalid Shotgun %s id %s, it must be a number." % (
                            entity_type,
                            entity_key,
                        )
                    )
                    return

                self.server.sync_in_jira(
                    settings_name,
                    entity_type,
                    int(entity_key),
                    event=payload,
                    **parameters
                )
            elif direction == "jira2sg":
                if not entity_type or not entity_key:
                    # We can't retrieve this easily from the webhook payload without
                    # hard coding a list of supported resource types, so we require
                    # it to be specified in the path for the time being.
                    self.send_error(
                        400,
                        "Invalid request path %s, it must include a Jira resource "
                        "type and its key" % self.path
                    )
                    return
                # Settings name/Jira Resource type/Jira Resource key
                self.server.sync_in_shotgun(
                    settings_name,
                    entity_type,
                    entity_key,
                    event=payload,
                    **parameters
                )
            else:
                self.send_error(
                    400,
                    "Invalid request path %s, don't know how to handle %s" % (
                        self.path,
                        direction
                    )
                )
                return
            self.send_response(200, "POST request successful")
            self.end_headers()
        except Exception as e:
            self.send_error(500, e.message)

    def log_message(self, format, *args):
        """
        Override :class:`BaseHTTPServer.BaseHTTPRequestHandler` method to use a
        standard logger.

        :param str format: A format string, e.g. '%s %s'.
        :param args: Arbitrary list of arguments to use with the format string.
        """
        message = "%s - %s" % (self.client_address[0], format % args)
        logger.info(message)

    def log_error(self, format, *args):
        """
        Override :class:`BaseHTTPServer.BaseHTTPRequestHandler` method to use a
        standard logger.

        :param str format: A format string, e.g. '%s %s'.
        :param args: Arbitrary list of arguments to use with the format string.
        """
        message = "%s - %s" % (self.client_address[0], format % args)
        logger.error(message)


def create_server(port, settings, keyfile=None, certfile=None):
    """
    Create the server.

    :param int port: A port number to listen to.
    :param str settings: Path to settings file.
    :param str keyfile: Optional path to a PEM key file to run in https mode.
    :param str certfile:  Optional path to a PEM certificate file to run in https mode.

    :returns: The HTTP Server
    :type: :class:`BaseHTTPServer.BaseHTTPRequestHandler`
    """
    httpd = Server(
        settings,
        ("localhost", port), RequestHandler
    )
    if keyfile and certfile:
        # Activate https
        httpd.socket = ssl.wrap_socket(
            httpd.socket,
            keyfile=keyfile,
            certfile=certfile,
            server_side=True
        )
    return httpd


def run_server(port, settings, keyfile=None, certfile=None):
    """
    Run the server until a shutdown is requested.

    :param int port: A port number to listen to.
    :param str settings: Path to settings file.
    :param str keyfile: Optional path to a PEM key file to run in https mode.
    :param str certfile:  Optional path to a PEM certificate file to run in https mode.
    """
    create_server(port, settings, keyfile, certfile).serve_forever()


def main():
    """
    Retrieve command line arguments and start the server.
    """
    parser = sg_jira.get_default_argument_parser()

    args = parser.parse_args()

    keyfile = None
    certfile = None
    if args.ssl_context:
        keyfile, certfile = args.ssl_context

    run_server(
        port=args.port,
        settings=args.settings,
        keyfile=keyfile,
        certfile=certfile,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print "Shutting down..."
