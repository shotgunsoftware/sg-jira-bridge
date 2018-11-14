# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import logging

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
    # We don't filter out any event and let the bridge deal with events which
    # should be ignored or processed.
    event_filter = None
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
    import sg_jira
    sg_jira.treat_sg_event(event)
    logger.debug("Processing %s" % event)
