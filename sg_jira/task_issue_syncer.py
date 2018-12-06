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
        """
        Process the given Shotgun event for the given Shotgun Entity

        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event was successfully processed, False if the
                  sync didn't happen for any reason.
        """
        task_fields = [
            "content"
            "task_assignees",
            "project",
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
            SHOTGUN_JIRA_TYPE_FIELD,
            SHOTGUN_JIRA_ID_FIELD
        ]
        sg_entity = self.shotgun.find_one(
            entity_type,
            [["id", "is", entity_id]],
            task_fields
        )
        if not sg_entity:
            self._logger.warning("Unable to retrieve a %s with id %d" % (
                entity_type,
                entity_id
            ))
            return False
        # Check if the Project is linked to a Jira Project
        jira_project_key = sg_entity["project.Project.%s" % SHOTGUN_JIRA_ID_FIELD]
        if not jira_project_key:
            self._logger.debug(
                "Skipping event %s for %s(%d) for Project %s "
                "not linked to a Jira Project" % (
                    event,
                    entity_type,
                    entity_id,
                    sg_entity["project"],
                )
            )
            return False
        jira_project = self.get_jira_project(jira_project_key)
        if not jira_project:
            raise RuntimeError(
                "Unable to retrieve a Jira Project %s for Shotgun Project %s" % (
                    jira_project_key,
                    sg_entity["project"],
                )
        )
        jira_issue = None
        if sg_entity[SHOTGUN_JIRA_ID_FIELD]:
            # Retrieve the Jira Issue
            jira_issue = self.get_jira_issue(sg_entity[SHOTGUN_JIRA_ID_FIELD])
        # Create it if needed
        # Update it
        self._logger.info("Syncing in Jira %s(%d) for event %s" % (
            entity_type,
            entity_id,
            event
        ))

        return True
