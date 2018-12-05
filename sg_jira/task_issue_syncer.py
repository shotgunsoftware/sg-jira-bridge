# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from .syncer import Syncer
from .constants import SHOTGUN_JIRA_TYPE_FIELD, SHOTGUN_JIRA_ID_FIELD


class TaskIssueSyncer(Syncer):
    """
    Sync Shotgun Tasks as Jira Issues.
    """

    def setup(self):
        """
        Check the Jira and Shotgun site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """
        self.bridge.assert_shotgun_field("Task", SHOTGUN_JIRA_ID_FIELD, "text")
        self.bridge.assert_shotgun_field("Task", SHOTGUN_JIRA_TYPE_FIELD, "text")

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :returns: True if the event is accepted for processing, False otherwise.
        """
        # We only accept Tasks
        if entity_type != "Task":
            return False
        # Check base implementation
        ret = super(TaskIssueSyncer, self).accept_shotgun_event(
            entity_type,
            entity_id,
            event
        )
        return ret

    def process_shotgun_event(self, entity_type, entity_id, event):
        # Find a matching Issue in Jira
        # Create it if needed
        # Update it
        pass
