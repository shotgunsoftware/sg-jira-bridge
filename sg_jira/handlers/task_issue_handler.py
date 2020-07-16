# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from ..constants import (
    SHOTGUN_JIRA_ID_FIELD,
    SHOTGUN_SYNC_IN_JIRA_FIELD,
    SHOTGUN_JIRA_URL_FIELD,
)
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
        "est_in_mins": "timetracking",  # time tracking needs to be enabled in Jira.
        "addressings_cc": None,
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
        "timetracking": "est_in_mins",  # time tracking needs to be enabled in Jira.
        "watches": "addressings_cc",
    }

    @property
    def _sg_jira_status_mapping(self):
        """
        Return a dictionary where keys are Shotgun status short codes and values
        Jira Issue status names.
        """
        return {
            "wtg": "To Do",
            "rdy": "Open",
            "ip": "In Progress",
            "fin": "Done",
            "hld": "Backlog",
            "omt": "Closed",
        }

    @property
    def _supported_shotgun_fields_for_jira_event(self):
        """"
        Return the list of fields this handler can process for a Jira event.

        :returns: A list of strings.
        """
        # By convention we might have `None` as values in our mapping dictionary
        # meaning that we handle a specific Jira field but there is not a direct
        # mapping to a Shotgun field and a special logic must be implemented
        # and called to perform the update to Shotgun.
        return [field for field in self.__ISSUE_FIELDS_MAPPING.itervalues() if field]

    def setup(self):
        """
        Check the Jira and Shotgun site, ensure that the sync can safely happen.
        This can be used as well to cache any value which is slow to retrieve.
        """
        self._shotgun.assert_field(
            "Task", SHOTGUN_JIRA_ID_FIELD, "text", check_unique=True
        )
        self._shotgun.assert_field("Task", SHOTGUN_SYNC_IN_JIRA_FIELD, "checkbox")
        self._shotgun.assert_field("Task", SHOTGUN_JIRA_URL_FIELD, "url")

    def _supported_shotgun_fields_for_shotgun_event(self):
        """
        Return the list of Shotgun fields that this handler can process for a
        Shotgun to Jira event.
        """
        return self.__TASK_FIELDS_MAPPING.keys()

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :returns: `True` if the event is accepted for processing, `False` otherwise.
        """
        # We only accept Tasks
        if entity_type != "Task":
            return False

        meta = event["meta"]
        field = meta["attribute_name"]

        # Note: we don't accept events for the SHOTGUN_SYNC_IN_JIRA_FIELD field
        # but we process them. Accepting the event is done by a higher level handler.
        # Events are accepted by a single handler, which is safer than letting
        # multiple handlers accept the same event: this allows the logic of processing
        # to be easily controllable and understandable.
        # However, there are cases where we want to re-use the processing logic.
        # For example, when the sync in jira checkbox is turned on, we want to
        # sync the task, and then its notes.
        # This processing logic is already available in the `TaskIssueHandler`
        # and the `NoteCommentHandler`. So the `EnableSyncingHandler` accepts
        # the event, and then call `TaskIssueHandler.process_shotgun_event` and,
        # only if this was successful, `NoteCommentHandler.process_shotgun_event`.

        if field not in self._supported_shotgun_fields_for_shotgun_event():
            self._logger.debug(
                "Rejecting Shotgun event for unsupported Shotgun field %s: %s"
                % (field, event)
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
        meta = event["meta"]
        shotgun_field = meta["attribute_name"]

        task_fields = [
            "content",
            "task_assignees",
            "created_by",
            "project",
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
            SHOTGUN_JIRA_ID_FIELD,
            SHOTGUN_SYNC_IN_JIRA_FIELD,
        ] + self._supported_shotgun_fields_for_shotgun_event()

        sg_entity = self._shotgun.consolidate_entity(
            {"type": entity_type, "id": entity_id}, fields=task_fields
        )
        if not sg_entity:
            self._logger.warning(
                "Unable to find Shotgun %s (%s)" % (entity_type, entity_id)
            )
            return False

        # Explicit sync: check if the "Sync in Jira" checkbox is on.
        if not sg_entity[SHOTGUN_SYNC_IN_JIRA_FIELD]:
            self._logger.debug(
                "Not syncing Shotgun entity %s. 'Sync in Jira' is off" % sg_entity,
            )
            return False

        # Check if the Project is linked to a Jira Project
        jira_project_key = sg_entity["project.Project.%s" % SHOTGUN_JIRA_ID_FIELD]
        if not jira_project_key:
            self._logger.debug(
                "Skipping Shotgun event for %s (%d). Entity's Project %s "
                "is not linked to a Jira Project. Event: %s"
                % (entity_type, entity_id, sg_entity["project"], event,)
            )
            return False
        jira_project = self.get_jira_project(jira_project_key)
        if not jira_project:
            self._logger.warning(
                "Unable to find a Jira Project %s for Shotgun Project %s"
                % (jira_project_key, sg_entity["project"],)
            )
            return False

        # When an Entity is created in Shotgun, a unique event is generated for
        # each field value set in the creation of the Entity. These events
        # have an additional "in_create" key in the metadata, identifying them
        # as events from the initial create event.
        #
        # When the bridge processes the first event, it loads all of the Entity
        # field values from Shotgun and creates the Jira Issue with those
        # values. So the remaining Shotgun events with the "in_create"
        # metadata key can be ignored since we've already handled all of
        # those field updates.

        # We use the Jira id field value to check if we're processing the first
        # event. If it exists with in_create, we know the comment has already
        # been created.
        if sg_entity[SHOTGUN_JIRA_ID_FIELD] and meta.get("in_create"):
            self._logger.debug(
                "Rejecting Shotgun event for %s.%s field update during "
                "create. Issue was already created in Jira: %s"
                % (sg_entity["type"], shotgun_field, event)
            )
            return False

        jira_issue = None
        if sg_entity[SHOTGUN_JIRA_ID_FIELD]:
            # Retrieve the Jira Issue
            jira_issue = self._get_jira_issue_and_validate(
                sg_entity[SHOTGUN_JIRA_ID_FIELD], sg_entity
            )
            if not jira_issue:
                return False

        # Create it if needed
        if not jira_issue:
            jira_issue = self._create_jira_issue_for_entity(
                sg_entity,
                jira_project,
                self._issue_type,
                summary=sg_entity["content"],
                timetracking={
                    "originalEstimate": "%d m" % (sg_entity["est_in_mins"] or 0)
                },
            )
            self._shotgun.update(
                sg_entity["type"],
                sg_entity["id"],
                {
                    SHOTGUN_JIRA_ID_FIELD: jira_issue.key,
                    SHOTGUN_JIRA_URL_FIELD: {
                        "url": jira_issue.permalink(),
                        "name": "View in Jira",
                    },
                },
            )

        sg_field = event["meta"]["attribute_name"]

        # Note: we don't accept events for the SHOTGUN_SYNC_IN_JIRA_FIELD field
        # but we process them. Accepting the event is done by a higher level handler.
        if sg_field == SHOTGUN_SYNC_IN_JIRA_FIELD:
            # If sg_sync_in_jira was turned on, sync all supported values
            # Note: if the Issue was just created, we might be syncing some
            # values a second time. This seems safer than checking which fields
            # are accepted in the the Issue create meta and trying to be smart here.
            # The efficiency cost does not seem high, except maybe for any fields
            # requiring a user lookup. But this could be handled by caching
            # retrieved users
            self._sync_shotgun_fields_to_jira(
                sg_entity, jira_issue,
            )
            return True

        # Otherwise, handle the attribute change
        self._logger.info(
            "Syncing Shotgun %s.%s (%d) to Jira %s %s"
            % (
                entity_type,
                sg_field,
                entity_id,
                jira_issue.fields.issuetype.name,
                jira_issue.key,
            )
        )
        self._logger.debug("Shotgun event: %s" % event)

        try:
            # Note: the returned jira_field will be None for the special cases handled
            # below.
            jira_field, jira_value = self._get_jira_issue_field_sync_value(
                jira_project,
                jira_issue,
                sg_entity["type"],
                sg_field,
                event["meta"].get("added"),
                event["meta"].get("removed"),
                event["meta"].get("new_value"),
            )
        except InvalidShotgunValue as e:
            self._logger.warning(
                "Unable to update Jira %s %s: %s"
                % (jira_issue.fields.issuetype.name, jira_issue.key, e,)
            )
            self._logger.debug("%s" % e, exc_info=True)
            return False

        if jira_field:
            self._logger.debug(
                "Updating %s to %s in Jira for %s"
                % (jira_field, jira_value, jira_issue)
            )
            jira_issue.update(fields={jira_field: jira_value})
            return True

        # Special cases not handled by a direct update
        if sg_field == "sg_status_list":
            shotgun_status = event["meta"]["new_value"]
            return self._sync_shotgun_status_to_jira(
                jira_issue,
                shotgun_status,
                "Updated from Shotgun %s (%d) moving to %s"
                % (entity_type, entity_id, shotgun_status),
            )
        if sg_field == "addressings_cc":
            self._sync_shotgun_cced_changes_to_jira(
                jira_issue, event["meta"]["added"], event["meta"]["removed"],
            )
            return True
        return False

    def _get_jira_issue_field_for_shotgun_field(
        self, shotgun_entity_type, shotgun_field
    ):
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

    def _get_shotgun_entity_field_for_issue_field(self, jira_field_id):
        """
        Returns the Shotgun field name to use to sync the given Jira Issue field.

        :param str jira_field_id: A Jira Issue field id, e.g. 'summary'.
        :returns: A string or `None`.
        """
        return self.__ISSUE_FIELDS_MAPPING.get(jira_field_id)

    def _sync_shotgun_fields_to_jira(
        self, sg_entity, jira_issue, exclude_shotgun_fields=None
    ):
        """
        Update the given Jira Issue with values from the given Shotgun Entity.

        An optional list of Shotgun fields can be provided to exclude them from
        the sync.

        :param sg_entity: A Shotgun Entity dictionary.
        :param jira_issue: A :class:`jira.Issue` instance.
        :param exclude_shotgun_fields: An optional list of Shotgun field names which
                                       shouldn't be synced.
        """

        if exclude_shotgun_fields is None:
            exclude_shotgun_fields = []

        issue_data = {}
        for sg_field, jira_field in self.__TASK_FIELDS_MAPPING.iteritems():
            if sg_field in exclude_shotgun_fields:
                continue

            if jira_field is None:
                # Special cases where a direct update is not possible, handled
                # below.
                continue

            shotgun_value = sg_entity[sg_field]
            if isinstance(shotgun_value, list):
                removed = []
                added = shotgun_value
                new_value = None
            else:
                removed = None
                added = None
                new_value = shotgun_value
            try:
                jira_field, jira_value = self._get_jira_issue_field_sync_value(
                    jira_issue.fields.project,
                    jira_issue,
                    sg_entity["type"],
                    sg_field,
                    added,
                    removed,
                    new_value,
                )
                if jira_field:
                    issue_data[jira_field] = jira_value
            except InvalidShotgunValue as e:
                self._logger.warning(
                    "Unable to update Jira %s %s field from Shotgun value %s: %s"
                    % (
                        jira_issue.fields.issuetype.name,
                        jira_issue.key,
                        shotgun_value,
                        e,
                    )
                )
                self._logger.debug("%s" % e, exc_info=True)
        if issue_data:
            self._logger.debug("Updating Jira %s with %s" % (jira_issue, issue_data))
            jira_issue.update(fields=issue_data)

        # Sync status
        if "sg_status_list" not in exclude_shotgun_fields:
            self._sync_shotgun_status_to_jira(
                jira_issue,
                sg_entity["sg_status_list"],
                "Updated from Shotgun %s(%d) moving to %s"
                % (sg_entity["type"], sg_entity["id"], sg_entity["sg_status_list"]),
            )
        # Sync addressings_cc
        if (
            "addressings_cc" not in exclude_shotgun_fields
            and sg_entity["addressings_cc"]
        ):
            self._sync_shotgun_cced_changes_to_jira(
                jira_issue, sg_entity["addressings_cc"], [],
            )
