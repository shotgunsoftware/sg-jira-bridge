# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from .syncer import Syncer
from .constants import SHOTGUN_JIRA_ID_FIELD


class TaskIssueSyncer(Syncer):
    """
    Sync Shotgun Tasks as Jira Issues.
    """
    def __init__(self, issue_type="Task", **kwargs):
        """
        Instatiate a new Task/Issue syncer for the given bridge.

        :param str issue_type: Jira Issue type to use when creating new Issues.
        """
        self._issue_type = issue_type
        super(TaskIssueSyncer, self).__init__(**kwargs)

    def setup(self):
        """
        Check the Jira and Shotgun site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """
        self.bridge.assert_shotgun_field("Task", SHOTGUN_JIRA_ID_FIELD, "text")

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event meta data for the change.
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
            "content",
            "task_assignees",
            "project",
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
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
        if not jira_issue:
            self._logger.info("Creating Jira Issue in %s for %s" % (
                jira_project,
                sg_entity,
            ))
            jira_issue = self.create_jira_issue_for_entity(
                sg_entity,
                jira_project,
                self._issue_type,
                summary=sg_entity["content"]
            )
            self.shotgun.update(
                sg_entity["type"],
                sg_entity["id"],
                {SHOTGUN_JIRA_ID_FIELD: jira_issue.key}
            )
        # Update it
        self._logger.info("Syncing in Jira %s(%d) to %s for event %s" % (
            entity_type,
            entity_id,
            jira_issue,
            event
        ))
        return True

    def accept_jira_event(self, resource_type, resource_id, event):
        """
        Accept or reject the given event for the given Jira resource.

        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event is accepted for processing, False otherwise.
        """
        if resource_type.lower() != "issue":
            self._logger.debug("Rejecting event for a %s Jira resource" % resource_type)
            return False
        # Check the event payload and reject the event if we don't have what we
        # expect
        jira_issue = event.get("issue")
        if not jira_issue:
            self._logger.debug("Rejecting event %s without an issue" % event)
            return False

        webhook_event = event.get("webhookEvent")
        if not webhook_event or webhook_event not in ["jira:issue_updated", "jira:issue_created"]:
            self._logger.debug(
                "Rejecting event %s with an unsupported webhook event %s" % (event, webhook_event)
            )
            return False

        changelog = event.get("changelog")
        if not changelog:
            self._logger.debug("Rejecting event %s without a changelog" % event)
            return False

        fields = jira_issue.get("fields")
        if not fields:
            self._logger.debug("Rejecting event %s without issue fields" % event)
            return False

        issue_type = fields.get("issuetype")
        if not issue_type:
            self._logger.debug("Rejecting event %s without an unknown issue type" % event)
            return False
        if issue_type["name"] != self._issue_type:
            self._logger.debug("Rejecting event %s without a %s issue type" % (event, issue_type["name"]))
            return False

        shotgun_id = fields.get(self.bridge.jira_shotgun_id_field)
        shotgun_type = fields.get(self.bridge.jira_shotgun_type_field)
        if not shotgun_id or not shotgun_type:
            self._logger.debug(
                "Rejecting event %s for %s %s not linked to a Shotgun Entity" % (
                    event,
                    issue_type["name"],
                    resource_id,
                )
            )
            return False

        return super(TaskIssueSyncer, self).accept_jira_event(
            resource_type,
            resource_id,
            event
        )

    def process_jira_event(self, resource_type, resource_id, event):
        """
        Process the given Jira event for the given Jira resource.

        :param str resource_type: The type of Jira resource to sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        """
        jira_issue = event["issue"]
        fields = jira_issue["fields"]
        issue_type = fields["issuetype"]

        shotgun_id = fields.get(self.bridge.jira_shotgun_id_field)
        if not shotgun_id.isdigit():
            raise ValueError(
                "Invalid Shotgun id %s, it should be an integer" % shotgun_id
            )
        shotgun_type = fields.get(self.bridge.jira_shotgun_type_field)
        sg_entity = self.bridge.shotgun.find_one(
            shotgun_type,
            [["id", "is", int(shotgun_id)]]
        )
        if not sg_entity:
            self._logger.warning("Unable to retrieve Shotgun %s (%s)" % (
                shotgun_type,
                shotgun_id
            ))
            return False

        self._logger.info("Syncing %s(%s) to Shotgun %s for event %s" % (
            issue_type["name"],
            resource_id,
            sg_entity,
            event
        ))
        return True

