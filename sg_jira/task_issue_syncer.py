# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from .syncer import Syncer
from .constants import SHOTGUN_JIRA_ID_FIELD

from .errors import InvalidShotgunValue, InvalidJiraValue


class TaskIssueSyncer(Syncer):
    """
    Sync Shotgun Tasks as Jira Issues.
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

    def __init__(self, issue_type="Task", **kwargs):
        """
        Instatiate a new Task/Issue syncer for the given bridge.

        :param str issue_type: Jira Issue type to use when creating new Issues.
        """
        self._issue_type = issue_type
        super(TaskIssueSyncer, self).__init__(**kwargs)

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

    def supported_shotgun_fields(self, shotgun_entity_type):
        """
        Return the list of Shotgun fields that this syncer can process for the
        given Shotgun Entity type.
        """
        if shotgun_entity_type != "Task":
            return []
        return self.__TASK_FIELDS_MAPPING.keys()

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

    def get_shotgun_entity_field_for_issue_field(self, jira_resource_type, jira_field_id):
        """
        Returns the Shotgun field name to use to sync the given Jira Issue field.

        :param str jira_resource_type: A Jira resource type, e.g. 'Issue'.
        :param str jira_field_id: A Jira resource field id, e.g. 'summary'.
        :returns: A string or `None`.
        """
        if jira_resource_type != "Issue":
            return None
        return self.__ISSUE_FIELDS_MAPPING.get(jira_field_id)

    def setup(self):
        """
        Check the Jira and Shotgun site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """
        self.shotgun.assert_field("Task", SHOTGUN_JIRA_ID_FIELD, "text")

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
            "created_by",
            "project",
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
            SHOTGUN_JIRA_ID_FIELD
        ]
        sg_entity = self.consolidate_shotgun_entity(
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
                summary=sg_entity["content"]
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
            self._logger.debug("Rejecting event %s with an unknown issue type" % event)
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
        # Collect the list of fields we might need to process the event
        # By convention we might have `None` as values in our mapping dictionary
        # meaning that we handle a specific Jira field but there is not a direct
        # mapping to a Shotgun field and a special logic must be implemented
        # and called to perform the update to Shotgun.
        sg_fields = [field for field in self.__ISSUE_FIELDS_MAPPING.itervalues() if field]
        sg_entity = self.consolidate_shotgun_entity(
            {"type": shotgun_type, "id": int(shotgun_id)},
            fields=sg_fields,
        )
        if not sg_entity:
            # Note: For the time being we don't allow Jira to create new Shotgun
            # Entities.
            self._logger.warning("Unable to retrieve Shotgun %s (%s)" % (
                shotgun_type,
                shotgun_id
            ))
            return False

        self._logger.info("Syncing %s(%s) to Shotgun %s(%d) for event %s" % (
            issue_type["name"],
            resource_id,
            sg_entity["type"],
            sg_entity["id"],
            event
        ))

        # The presence of the changelog key has been validated by the accept method.
        changes = event["changelog"]["items"]
        shotgun_data = {}
        for change in changes:
            # Depending on the Jira server version, we can get the Jira field id
            # in the change payload or just the field nmae.
            # If we don't have the field id, retrieve it from our internal mapping.
            field_id = change.get("fieldId") or self.bridge.get_jira_issue_field_id(
                change["field"]
            )
            self._logger.debug(
                "Treating change %s for field %s" % (
                    change, field_id
                )
            )
            try:
                shotgun_field, shotgun_value = self.get_shotgun_entity_field_sync_value(
                    sg_entity,
                    jira_issue,
                    field_id,
                    change,
                )
                if shotgun_field:
                    shotgun_data[shotgun_field] = shotgun_value
            except InvalidJiraValue as e:
                self._logger.warning(
                    "Unable to update Shotgun %s for event %s: %s" % (
                        jira_issue,
                        event,
                        e,
                    )
                )

        if shotgun_data:
            self._logger.debug(
                "Updating Shotgun %s (%d) with %s" % (
                    sg_entity["type"],
                    sg_entity["id"],
                    shotgun_data,
                )
            )
            self.shotgun.update(
                sg_entity["type"],
                sg_entity["id"],
                shotgun_data,
            )
            return True

        return False

