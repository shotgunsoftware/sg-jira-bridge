# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import logging
import time
from daemonize import Daemonize
import argparse
import signal

DESCRIPTION = """
Run the SG Jira web app as a Linux service.
"""
logger = logging.getLogger("service")
# Ensure basic logging is always enabled
logging.basicConfig(format="%(levelname)s:%(name)s:%(message)s")
logger.setLevel(logging.DEBUG)

def start(log_file, pid_file, port_number, settings):
    keep_fds = []
    if log_file:
        fh = logging.FileHandler(log_file, "a")
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)
        keep_fds = [fh.stream.fileno()]

    def start_wep_app():
        import logging
        logger = logging.getLogger("sg_jira")
        logger.error("startup")
        try:
            import webapp
            webapp.run_server(
                port=port_number,
                settings=settings
            )
        except Exception as e:
            logger.exception(e)
        logger.warning("bye")

    daemon = Daemonize(
        app="sg_jira",
        pid=pid_file,
        action=start_wep_app,
        keep_fds=keep_fds
    )
    daemon.start()

def stop(pid_file):
    """
    Stop the daemon
    """
    # Get the pid from the pidfile
    pid = None
    with open(pid_file, "r") as pf:
        pid = int(pf.read().strip())

    if not pid:
        logger.error("Unable to retrieve pid from %s" % pid_file)
        return

    # Check if the process is still running
    try:
        os.kill(pid, 0)
    except OSError as e:
        logger.warning("Process %d is not running anymore." % pid)
    else:
        os.kill(pid, signal.SIGTERM)
        # Give the process some time to exit nicely
        time.sleep(0.1)
        # Send a SIGKILL signal but ignore errors
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    # Clean up
    if os.path.exists(pid_file):
        os.remove(pid_file)

def main():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION
    )
    parser.add_argument(
        "--pid_file",
        default="/tmp/sg_jira.pid",
        help="Full path to a file where to write the process pid.",
    )
    parser.add_argument(
        "--log_file",
        help="Full path to a file where to log output.",
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
        "action",
        choices=["start", "stop", "restart"],
        help="Action to perform.",
    )
    args = parser.parse_args()

    if args.action == "start":
        logger.info("Starting..")
        start(
            args.log_file,
            args.pid_file,
            args.port,
            os.path.abspath(args.settings),
        )
    elif args.action == "stop":
        logger.info("Stopping..")
        stop(args.pid_file)
    elif args.action == "restart":
        stop(args.pid_file)

if __name__ == "__main__":
    main()
