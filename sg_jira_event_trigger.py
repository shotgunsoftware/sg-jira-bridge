# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import logging
import requests

"""
A simple Shotgun event daemon plugin which sends all events to the SG/Jira bridge.
"""


def registerCallbacks(reg):
    """
    Register all necessary or appropriate callbacks for this plugin.

    Shotgun credentials are retrieved from the `SGDAEMON_SGJIRA_NAME` and `SGDAEMON_SGJIRA_KEY`
    environment variables.

    :param reg: A Shotgun Event Daemon Registrar instance.
    """
    # Narrow down the list of events we pass to the bridge
    event_filter = {
        "Shotgun_Task_Change": ["*"]
        "Shotgun_Ticket_Change": ["*"]
        "Shotgun_Project_Change": ["*"]
    }
    reg.registerCallback(
        os.environ["SGDAEMON_SGJIRA_NAME"],
        os.environ["SGDAEMON_SGJIRA_KEY"],
        process_event,
        event_filter,
        None,
    )

    # Set the logging level for this particular plugin. Let debug and above
    # messages through (don't block info, etc). This is particularly usefull
    # for enabling and disabling debugging on a per plugin basis.
    reg.logger.setLevel(logging.DEBUG)


def process_event(sg, logger, event, args):
    """
    A callback that logs its arguments.

    :param sg: Shotgun API handle.
    :param logger: Logger instance.
    :param event: A Shotgun EventLogEntry entity dictionary.
    :param args: Any additional misc arguments passed through this plugin.
    """
    logger.debug("Processing %s" % event)
    response = requests.post(
        "https://httpbin.org/post",
        data=payload
    )
    response.raise_for_status()
    logger.debug("Event successfully processed.")
