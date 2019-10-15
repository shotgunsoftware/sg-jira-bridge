# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import argparse

def get_default_argument_parser():
    """
    Get an argument parser for the settings and port number.
    """
    parser = argparse.ArgumentParser(
        description="A simple web app frontend to the SG Jira bridge."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9090,
        help="The port number to listen to.",
    )
    parser.add_argument(
        "--settings",
        help="Full path to settings file.",
        required=True
    )
    parser.add_argument(
        "--ssl_context",
        help="A key and certificate file pair to run the server in https mode.",
        nargs=2,
    )

    return parser