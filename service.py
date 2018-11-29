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

This script can be used with a systemd setup and handles the usual start, stop,
restart and status actions.

The running process daemonizes itself and its pid is stored in a pid file.
"""

logger = logging.getLogger("service")
# Ensure basic logging is always enabled
logging.basicConfig(format="%(levelname)s:%(name)s:%(message)s")
logger.setLevel(logging.DEBUG)


def status(pid_file):
    """
     Return the pid of the service if it is running.

    :param str pid_file: Full path to the pid file used by the service.
    :returns: The process pid as an int if it is running, `None` otherwise.
    """
    if not os.path.exists(pid_file):
        return None

    pid = None
    with open(pid_file, "r") as pf:
        pid = int(pf.read().strip())

    if not pid:
        logger.error("Unable to retrieve pid from %s" % pid_file)
        return None

    try:
        # Send 0 signal to check if the process is alive.
        os.kill(pid, 0)
    except OSError as e:
        logger.debug("%s" % e, exc_info=True)
        return None
    return pid


def start(pid_file, port_number, settings, log_file=None):
    """
    Start the service.

    :param str pid_file: Full path to the pid file used by the service.
    :param int port_number: The port number for the web app to listen on.
    :param str settings: Full path to settings file for the web app.
    :param str log_file: An optional log file to use for the daemon output. By
                         default the daemon uses a syslog handler.
    """
    keep_fds = []
    if log_file:
        fh = logging.FileHandler(log_file, "a")
        fh.setLevel(logging.INFO)
        logger.addHandler(fh)
        keep_fds = [fh.stream.fileno()]

    # Inline function so we can pass a callable to Daemonize with our parameters
    # set.
    def start_wep_app():
        import logging
        logger = logging.getLogger("sg_jira")
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
        keep_fds=keep_fds,
        logger=logger if log_file else None
    )
    daemon.start()


def stop(pid_file):
    """
    Stop the service if it is running.

    :param str pid_file: Full path to the pid file used by the service.
    """
    # Get the running process pid, if any
    pid = status(pid_file)
    if not pid:
        return

    try:
        os.kill(pid, signal.SIGTERM)
        # Give the process some time to exit nicely
        time.sleep(0.1)
        # Send a SIGKILL signal but ignore errors
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    except OSError as e:
        # Catch the error in case the process exited between our check and our
        # attempt to stop it.
        logger.warning(
            "Unable to stop process %d, assuming it is already stopped: %s" % (pid, e)
        )
        logger.debug(str(e), exc_info=True)
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
        help="The port number to listen on.",
    )
    parser.add_argument(
        "--settings",
        help="Full path to settings file.",
        required=True
    )
    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "status"],
        help="Action to perform.",
    )
    args = parser.parse_args()

    if args.action == "start":
        start(
            args.pid_file,
            args.port,
            os.path.abspath(args.settings),
            args.log_file,
        )
    elif args.action == "stop":
        stop(args.pid_file)
    elif args.action == "status":
        pid = status(args.pid_file)
        if pid:
            logger.info("Service is running with pid %d" % pid)
        else:
            logger.info("Service is not running.")
    elif args.action == "restart":
        stop(args.pid_file)
        start(
            args.pid_file,
            args.port,
            os.path.abspath(args.settings),
            args.log_file,
        )


if __name__ == "__main__":
    main()
