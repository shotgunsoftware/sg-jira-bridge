# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from .syncer import Syncer
from .constants import SHOTGUN_JIRA_ID_FIELD
from .handlers import TaskIssueHandler, NoteCommentHandler

from .errors import InvalidShotgunValue, InvalidJiraValue


class TaskIssueSyncer(Syncer):
    """
    Sync Shotgun Tasks as Jira Issues.
    """
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
    def handlers(self):
        """
        Return a list of :class:`SyncHandler` instances.
        """
        return [
            TaskIssueHandler(self, self._issue_type),
            NoteCommentHandler(self)
        ]

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
        sg_entity = self.shotgun.consolidate_entity(
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

