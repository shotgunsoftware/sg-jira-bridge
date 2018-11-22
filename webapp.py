# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import argparse
import urlparse
import BaseHTTPServer
import json

import sg_jira

DESCRIPTION = """
A simple web app frontend to the SG Jira bridge.
"""


class Server(BaseHTTPServer.HTTPServer):
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


class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_GET(self):
        """
        Handle a GET request.
        """
        self.send_response(200, "The server is alive")
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write("<html><body>The server is alive</body<></html>")
        self.wfile.close()

    def do_POST(self):
        """
        Handle a POST request.
        """
        try:
            # Extract path components from the path, ignore leading '/' and
            # discard empty values coming from '/' at the end or multiple
            # contiguous '/'
            path_parts = [x for x in self.path[1:].split("/") if x]
            if len(path_parts) != 4:
                self.send_error(400, "Invalid request path %s" % self.path)
                return
            # Extract additional query parameters
            parsed = urlparse.urlparse(self.path)
            parameters = {}
            if parsed.query:
                parameters = urlparse.parse_qs(parsed.query, True, True)
            # Read the body to get the payload
            content_type = self.headers.getheader("content-type")
            # Check the content type, if not set we assume json.
            if content_type and content_type != "application/json":
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
            if path_parts[0] == "sg2jira":
                # Settings name/SG Entity type/SG Entity id
                self.server.sync_in_jira(
                    path_parts[1],
                    path_parts[2],
                    int(path_parts[3]),
                    event=payload,
                )
            elif path_parts[0] == "jira2sg":
                # Settings name/Jira Resource type/Jira Resource key
                self.server.sync_in_shotgun(
                    path_parts[1],
                    path_parts[2],
                    path_parts[3],
                    event=payload,
                )
            else:
                self.send_error(
                    400,
                    "Invalid request path %s, don't know how ot handle %s" % (self.path, path_parts[0])
                )
                return
            self.send_response(200, "Post request successfull")
        except Exception as e:
            self.send_error(500, e.message)


def run_server(port, settings):
    """
    Run the server until a shutdown is requested.
    """
    httpd = Server(
        settings,
        ("localhost", port), RequestHandler
    )
    httpd.serve_forever()


def main():
    """
    Retrieve command line arguments and start the server.
    """
    parser = argparse.ArgumentParser(
        description=DESCRIPTION
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9000,
        help="The port number to listen to.",
        required=True
    )
    parser.add_argument(
        "--settings",
        help="Full path to settings file.",
        required=True
    )
    args = parser.parse_args()
    run_server(
        port=args.port,
        settings=args.settings,
    )


if __name__ == "__main__":
    main()
