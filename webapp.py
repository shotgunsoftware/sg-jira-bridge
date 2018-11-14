# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import argparse
import urlparse
import BaseHTTPServer
import SocketServer

DESCRIPTION = """
A simple web app frontend to the SG Jira bridge.
"""

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
            if not path_parts:
                self.send_error(400, "Invalid request path %s" % self.path)
                return
            # Basic routing: extract the synch direction and additional values
            # from the path
            if path_parts[0] == "sg2jira":
                pass
            elif path_parts[0] == "jira2sg":
                pass
            else:
                self.send_error(400, "Invalid request path %s" % self.path)
                return
            parsed = urlparse.urlparse(self.path)
            content_len = int(self.headers.getheader("content-length", 0))
            post_body = self.rfile.read(content_len)
            self.send_response(200, "Post request successfull")
        except Exception as e:
            self.send_error(500, e.message)

def run_server(port=9000):
    """
    Run the server until a shutdown is requested.
    """
    httpd = BaseHTTPServer.HTTPServer(
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
        help="The port number to listen to."
    )
    args = parser.parse_args()
    run_server(port=args.port)

if __name__ == "__main__":
    main()
