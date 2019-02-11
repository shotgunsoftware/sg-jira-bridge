# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from ..constants import SHOTGUN_JIRA_ID_FIELD
from ..errors import InvalidShotgunValue
from .entity_issue_handler import EntityIssueHandler


class TaskIssueHandler(EntityIssueHandler):
    """
    Sync a Shotgun Task as a Jira Issue.
    """
    # Define the mapping between Shotgun Task fields and Jira Issue fields
    # if the Jira target is None, it means the target field is not settable
    # directly.
    __TASK_FIELDS_MAPPING = {
        "content": "summary",
        "sg_description": "description",
        "sg_status_list": None,
        "task_assignees": "assignee",
        "tags": "labels",
        "created_by": "reporter",
        "due_date": "duedate",
        "est_in_mins": "timetracking", # time tracking needs to be enabled in Jira.
        "addressings_cc": None
    }

    # Define the mapping between Jira Issue fields and Shotgun Task fields
    # if the Shotgun target is None, it means the target field is not settable
    # directly.
    __ISSUE_FIELDS_MAPPING = {
        "summary": "content",
        "description": "sg_description",
        "status": "sg_status_list",
        "assignee": "task_assignees",
        "labels": "tags",
        "duedate": "due_date",
        "timetracking": "est_in_mins", # time tracking needs to be enabled in Jira.
        "watches": "addressings_cc"
    }

    @property
    def sg_jira_statuses_mapping(self):
        """
        Return a dictionary where keys are Shotgun status short codes and values
        Jira Issue status names.
        """
        return {
            "ip": "In Progress",
            "fin": "Done",
            "res": "Done",
            "rdy": "Selected for Development", # Used to be "To Do" ?
            "wtg": "Selected for Development",
            "hld": "Backlog",
        }

    @property
    def supported_shotgun_fields_for_jira_event(self):
        """"
        Return the list of fields this handler can process for a Jira event.

        :returns: A list of strings.
        """
        # By convention we might have `None` as values in our mapping dictionary
        # meaning that we handle a specific Jira field but there is not a direct
        # mapping to a Shotgun field and a special logic must be implemented
        # and called to perform the update to Shotgun.
        return [
            field for field in self.__ISSUE_FIELDS_MAPPING.itervalues() if field
        ]

    def setup(self):
        """
        Check the Jira and Shotgun site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """
        self.shotgun.assert_field("Task", SHOTGUN_JIRA_ID_FIELD, "text")

    def supported_shotgun_fields_for_shotgun_event(self):
        """
        Return the list of Shotgun fields that this handler can process for a
        Shotgun to Jira event.
        """
        return self.__TASK_FIELDS_MAPPING.keys()

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :returns: `True if the event is accepted for processing, `False` otherwise.
        """
        # We only accept Tasks
        if entity_type != "Task":
            return False

        meta = event["meta"]
        field = meta["attribute_name"]
        if field not in self.supported_shotgun_fields_for_shotgun_event():
            self._logger.debug(
                "Rejecting event %s with unsupported or missing field %s." % (
                    event, field
                )
            )
            return False

        return True

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
            "created_by",
            "project",
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
            SHOTGUN_JIRA_ID_FIELD
        ] + self.__TASK_FIELDS_MAPPING.keys()
        sg_entity = self.shotgun.consolidate_entity(
            {"type": entity_type, "id": entity_id},
            fields=task_fields
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
                summary=sg_entity["content"],
                timetracking={
                    "originalEstimate": "%d m" % (sg_entity["est_in_mins"] or 0)
                }
            )
            self.shotgun.update(
                sg_entity["type"],
                sg_entity["id"],
                {SHOTGUN_JIRA_ID_FIELD: jira_issue.key}
            )
        # Update it
        self._logger.debug("Syncing in Jira %s(%d) to %s for event %s." % (
            entity_type,
            entity_id,
            jira_issue,
            event
        ))
        sg_field = event["meta"]["attribute_name"]

        try:
            # Note: the returned jira_field will be None for the special cases handled
            # below.
            jira_field, jira_value = self.get_jira_issue_field_sync_value(
                jira_project,
                jira_issue,
                sg_entity["type"],
                sg_field,
                event["meta"]
            )
        except InvalidShotgunValue as e:
            self._logger.warning(
                "Unable to update Jira %s for event %s: %s" % (
                    jira_issue,
                    event,
                    e,
                )
            )
            self._logger.debug("%s" % e, exc_info=True)
            return False

        if jira_field:
            self._logger.debug("Updating Jira %s with %s: %s" % (
                jira_issue,
                jira_field,
                jira_value
            ))
            jira_issue.update(fields={jira_field: jira_value})
            return True

        # Specials cases not handled by a direct update
        if sg_field == "sg_status_list":
            shotgun_status = event["meta"]["new_value"]
            return self.sync_shotgun_status_to_jira(
                jira_issue,
                shotgun_status,
                "Updated from Shotgun %s(%d) moving to %s" % (
                    entity_type,
                    entity_id,
                    shotgun_status
                )

            )
        if sg_field == "addressings_cc":
            self.sync_shotgun_cced_changes_to_jira(
                jira_issue,
                event["meta"]["added"],
                event["meta"]["removed"],
            )
            return True
        return False

    def get_jira_issue_field_for_shotgun_field(self, shotgun_entity_type, shotgun_field):
        """
        Returns the Jira Issue field id to use to sync the given Shotgun Entity
        type field.

        :param str shotgun_entity_type: A Shotgun Entity type, e.g. 'Task'.
        :param str shotgun_field: A Shotgun Entity field name, e.g. 'sg_status_list'.
        :returns: A string or `None`.
        """
        if shotgun_entity_type != "Task":
            return None
        return self.__TASK_FIELDS_MAPPING.get(shotgun_field)

    def get_shotgun_entity_field_for_issue_field(self, jira_field_id):
        """
        Returns the Shotgun field name to use to sync the given Jira Issue field.

        :param str jira_field_id: A Jira Issue field id, e.g. 'summary'.
        :returns: A string or `None`.
        """
        return self.__ISSUE_FIELDS_MAPPING.get(jira_field_id)
