# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import logging

# Import the syncer base class
from sg_jira import Syncer


class ExampleSync(Syncer):
    """
    A custom syncer example
    """

    def __init__(self, log_level=logging.WARNING, **kwargs):
        """
        Instantiate a new syncer with an additional parameter from the base class

        :param log_level: A standard logging level.
        """
        # Call base class init with all parameters we do not handle specifically
        super(ExampleSync, self).__init__(**kwargs)
        # Handle our additional parameter.
        self.logger.setLevel(log_level)

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Shotgun event for the given Shotgun Entity

        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event meta data for the change.
        """
        self.logger.info(
            "Syncing in Jira %s(%d) for event %s" % (entity_type, entity_id, event)
        )
