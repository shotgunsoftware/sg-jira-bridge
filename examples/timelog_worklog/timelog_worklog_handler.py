# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import datetime
import json

from jira import JIRAError

from sg_jira.constants import (SHOTGUN_JIRA_ID_FIELD,
                               SHOTGUN_SYNC_IN_JIRA_FIELD,
                               TIMELOG_FIELDS_MAPPING)
from sg_jira.handlers import SyncHandler


class TimelogWorklogHandler(SyncHandler):
    """
    A handler which syncs a Flow Production Tracking Timelog as a Jira Worklog.
    The sync works both ways (from PTR to Jira and from Jira to PTR)
    and handles creation, updating and deletion.
    """

    # Define the mapping between Flow Production Tracking Timelog fields and Jira Worklog fields
    __TIMELOG_FIELDS_MAPPING = TIMELOG_FIELDS_MAPPING

    # Define the name of the Jira custom field used to store PTR TimeLogs assignee
    # Because the Jira Api doesn't support worklog assignation, we need to find a
    # workaround to store the PTR TimeLog assignee
    __JIRA_SHOTGUN_TIMELOG_FIELD = "Shotgun TimeLogs"

    # Define the name of the attribute used to track when a Timelog is retired from Flow Production Tracking
    __SG_RETIREMENT_FIELD = "retirement_date"

    # Define the format of the Jira dates
    __JIRA_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"

    # Define the format of the Flow Production Tracking dates
    __SG_DATE_FORMAT = "%Y-%m-%d"

    def __init__(self, syncer, sync_sg_timelog_deletion, sync_jira_worklog_deletion):
        """
        Instantiate a handler for the given syncer.

        :param syncer: A :class:`~sg_jira.Syncer` instance.
        :param sync_sg_timelog_deletion: If True, when a worklog is deleted in Jira, it will also be deleted in Flow
            Production Tracking
        :param sync_jira_worklog_deletion: If True, when a timelog is deleted in Flow Production Tracking, it will also
            be deleted in Jira
        """
        super(TimelogWorklogHandler, self).__init__(syncer)

        self.__sync_sg_timelog_deletion = sync_sg_timelog_deletion
        self.__sync_jira_worklog_deletion = sync_jira_worklog_deletion

        # store the id of the Jira custom field used to store the TimeLogs users mapping
        self.__jira_sg_timelog_field = self._jira.get_jira_issue_field_id(
            self.__JIRA_SHOTGUN_TIMELOG_FIELD.lower()
        )

    @property
    def _sg_timelog_fields(self):
        """All the required fields when querying for PTR TimeLogs"""
        return [
            "created_by",
            "project",
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
            SHOTGUN_JIRA_ID_FIELD,
            "entity.Task.%s" % SHOTGUN_SYNC_IN_JIRA_FIELD,
        ] + self._supported_shotgun_fields_for_shotgun_event()

    @property
    def _sg_task_fields(self):
        """All the required fields when querying for PTR Task"""
        return [
            "project",
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
            SHOTGUN_JIRA_ID_FIELD,
            SHOTGUN_SYNC_IN_JIRA_FIELD,
        ]

    def setup(self):
        """
        Check the Jira and Flow Production Tracking site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """
        self._shotgun.assert_field(
            "TimeLog", SHOTGUN_JIRA_ID_FIELD, "text", check_unique=True
        )

    def _supported_shotgun_fields_for_shotgun_event(self):
        """
        Return the list of Flow Production Tracking fields that this handler can process for a
        Flow Production Tracking to Jira event.

        :returns: A list of strings.
        """
        return list(self.__TIMELOG_FIELDS_MAPPING.keys())

    def _supported_shotgun_fields_for_jira_event(self):
        """
        Return the list of Jira fields this handler can process for a Jira to Flow Production Tracking event.

        :returns: A list of strings.
        """
        # By convention, we might have `None` as values in our mapping dictionary
        # meaning that we handle a specific Jira field but there is not a direct
        # mapping to an PTR field and a special logic must be implemented
        # and called to perform the update to PTR.
        return [field for field in self.__TIMELOG_FIELDS_MAPPING.values() if field]

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Flow Production Tracking Entity.

        :returns: `True if the event is accepted for processing, `False` otherwise.
        """

        # We only accept TimeLog
        if entity_type != "TimeLog":
            return False

        meta = event["meta"]
        field = meta["attribute_name"]

        # Note: we don't accept events for the SHOTGUN_SYNC_IN_JIRA_FIELD field
        # but we process them. Accepting the event is done by a higher level handler.
        # Events are accepted by a single handler, which is safer than letting
        # multiple handlers accept the same event: this allows the logic of processing
        # to be easily controllable and understandable.
        # However, there are cases where we want to re-use the processing logic.
        # For example, when the Sync In Jira checkbox is turned on, we want to
        # sync the task, and then its notes and timelogs.
        # This processing logic is already available in the `TaskIssueHandler`
        # and the `TimelogWorklogHandler`. So the `EnableSyncingHandler` accepts
        # the event, and then calls `TaskIssueHandler.process_shotgun_event` and,
        # only if this was successful, `TimelogWorklogHandler.process_shotgun_event`.

        # in case the option sync the timelog deletion from PTR to Jira is set to True, we need to
        # add the retirement field to the list of supported fields
        supported_shotgun_fields = self._supported_shotgun_fields_for_shotgun_event()
        if self.__sync_jira_worklog_deletion:
            supported_shotgun_fields.append(self.__SG_RETIREMENT_FIELD)
        if field not in supported_shotgun_fields:
            self._logger.debug(
                "Rejecting Flow Production Tracking event for unsupported PTR field %s: %s"
                % (field, event)
            )
            return False

        # we only want to sync Timelogs linked to a Task which as the sync flag enabled
        retired_only = True if field == self.__SG_RETIREMENT_FIELD else False
        sg_timelog = self._shotgun.find_one(
            entity_type,
            [["id", "is", entity_id]],
            self._sg_timelog_fields,
            retired_only=retired_only,
        )
        if not sg_timelog:
            self._logger.debug(
                f"Rejecting Flow Production Tracking event for unfounded PTR entity {entity_type}: {entity_id}"
            )
            return False
        if not sg_timelog.get(
            "entity.Task.%s" % SHOTGUN_SYNC_IN_JIRA_FIELD
        ) and not sg_timelog.get("entity.Task.%s" % SHOTGUN_JIRA_ID_FIELD):
            self._logger.debug(
                f"Rejecting Flow Production Tracking event because {entity_type} ({entity_id}) "
                f"is not linked to a synced Task"
            )
            return False

        # When an Entity is created in PTR, a unique event is generated for
        # each field value set in the creation of the Entity. These events
        # have an additional "in_create" key in the metadata, identifying them
        # as events from the initial create event.
        #
        # When the bridge processes the first event, it loads all of the Entity
        # field values from PTR and creates the Jira Issue with those
        # values. So the remaining PTR events with the "in_create"
        # metadata key can be ignored since we've already handled all of
        # those field updates.

        # We use the Jira id field value to check if we're processing the first
        # event. If it exists with in_create, we know the timelog has already
        # been created.
        if sg_timelog[SHOTGUN_JIRA_ID_FIELD] and meta.get("in_create"):
            self._logger.debug(
                f"Rejecting Flow Production Tracking event for {entity_type}.{field} field update during "
                f"create. Worklog was already created in Jira: {event}"
            )
            return False

        return True

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Flow Production Tracking event for the given PTR Entity

        :param str entity_type: The PTR Entity type to sync.
        :param int entity_id: The id of the PTR Entity to sync.
        :param event: A dictionary with the event for the change.
        :returns: True if the event was successfully processed, False if the
                  sync didn't happen for any reason.
        """
        meta = event["meta"]
        shotgun_field = meta["attribute_name"]

        # Note: we don't accept events for the SHOTGUN_SYNC_IN_JIRA_FIELD field
        # but we process them.
        # Accepting the event is done by a higher level handler.
        if shotgun_field == SHOTGUN_SYNC_IN_JIRA_FIELD:
            # Note: in this case the Entity is a Task.
            # We only want to sync existing FTP Timelogs and Jira Worklogs
            return self._sync_existing_timelog_and_worklog(
                {"type": entity_type, "id": entity_id}
            )

        sg_timelog = self._shotgun.consolidate_entity(
            {"type": entity_type, "id": entity_id},
            fields=self._sg_timelog_fields,
            retired_only=True if shotgun_field == self.__SG_RETIREMENT_FIELD else False,
        )
        if not sg_timelog:
            self._logger.debug(
                f"Unable to find Flow Production Tracking {entity_type} ({entity_id})"
            )
            return False

        # In that case, we want to remove the associated Jira Worklog when a Timelog is removed from PTR
        if (
            shotgun_field == self.__SG_RETIREMENT_FIELD
            and self.__sync_jira_worklog_deletion
        ):
            return self._remove_timelog_from_jira(sg_timelog, update_sg=False)

        if shotgun_field == "entity":

            # Remove the timelog from Jira if it is not linked to a synced task anymore
            if meta.get("old_value") and meta["old_value"].get("type") == "Task":
                sg_task = self._shotgun.consolidate_entity(
                    meta["old_value"], fields=self._sg_task_fields
                )
                if sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD]:
                    return self._remove_timelog_from_jira(sg_timelog)

            # Add the timelog to Jira if it is linked to a synced task
            if meta.get("new_value") and meta["new_value"].get("type") == "Task":
                sg_task = self._shotgun.consolidate_entity(
                    meta["new_value"], fields=self._sg_task_fields
                )
                if sg_task[SHOTGUN_SYNC_IN_JIRA_FIELD]:
                    return self._add_timelog_to_jira(sg_timelog)
            return False

        self._logger.info(
            f"Flow Production Tracking Timelog ({sg_timelog['id']}).{shotgun_field} updated"
        )

        # Update the Jira timelog content
        return self._sync_timelog_content_to_jira(sg_timelog)

    def accept_jira_event(self, resource_type, resource_id, event):
        """
        Accept or reject the given event for the given Jira resource.

        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event is accepted for processing, False otherwise.
        """

        if resource_type.lower() != "issue":
            self._logger.debug(
                f"Rejecting event for a {resource_type} Jira resource. Handler only "
                "accepts Issue resources."
            )
            return False

        # Check the event payload and reject the event if we don't have what we
        # expect
        jira_worklog = event.get("worklog")
        if not jira_worklog:
            self._logger.debug(f"Rejecting event without a worklog: {event}")
            return False

        webhook_event = event.get("webhookEvent")
        if not webhook_event:
            self._logger.debug(f"Rejecting event without a webhookEvent: {event}")
            return False

        if webhook_event == "worklog_deleted" and not self.__sync_sg_timelog_deletion:
            self._logger.debug(
                f"Rejecting event with unsupported webhookEvent {webhook_event}."
            )
            return False

        # rejecting the worklog created event if it has been created by the Jira Bridge user
        # that means that the timelog was created from PTR and synced to Jira
        if webhook_event == "worklog_created":
            if jira_worklog["author"]["accountId"] == self._jira.myself()["accountId"]:
                self._logger.debug("Rejecting event created by the bridge user.")
                return False

        # rejecting the worklog updated event if it has been updated by the Jira Bridge user
        # that means that the timelog was updated from PTR
        if webhook_event == "worklog_updated":
            if (
                jira_worklog["updateAuthor"]["accountId"]
                == self._jira.myself()["accountId"]
            ):
                self._logger.debug("Rejecting event updated by the bridge user.")
                return False

        return True

    def process_jira_event(self, resource_type, resource_id, event):
        """
        Process the given Jira event for the given Jira resource.

        :param str resource_type: The type of Jira resource to sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event was successfully processed, False if the
                  sync didn't happen for any reason.
        """

        jira_worklog = event["worklog"]
        webhook_event = event["webhookEvent"]

        jira_issue = self.get_jira_issue(jira_worklog["issueId"])
        if not jira_issue:
            self._logger.debug(
                f"Couldn't find the JIRA issue ({jira_worklog['issueId']}) linked to the Worklog"
            )
            return False

        # construct our Jira key for TimeLog and check if we have an existing
        # Flow Production Tracking TimeLog to update
        # key format: <jira issue key>/<jira worklog id>
        sg_jira_key = "%s/%s" % (jira_issue.key, jira_worklog["id"])

        sg_timelogs = self._shotgun.find(
            "TimeLog",
            [[SHOTGUN_JIRA_ID_FIELD, "is", sg_jira_key]],
            fields=self._sg_timelog_fields,
        )

        if len(sg_timelogs) > 1:
            self._logger.debug(
                f"Unable to process Jira Worklog {webhook_event} event. More than one TimeLog "
                f"exists in Flow Production Tracking with Jira key {sg_jira_key}: {sg_timelogs}"
            )
            return False

        # get the PTR Task associated to the Jira Issue
        sg_tasks = self._shotgun.find(
            "Task",
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            fields=self._sg_task_fields,
        )

        if len(sg_tasks) > 1:
            self._logger.debug(
                f"Unable to process Jira Worklog {webhook_event} event. More than one Task "
                f"exists in Flow Production Tracking with Jira key {jira_issue.key}: {sg_tasks}"
            )
            return False
        elif len(sg_tasks) == 0:
            self._logger.debug(
                f"Unable to process Jira Worklog {webhook_event} event. Couldn't find any Task "
                f"in Flow Production Tracking with Jira key {jira_issue.key}"
            )
            return False

        if not sg_tasks[0][SHOTGUN_SYNC_IN_JIRA_FIELD]:
            self._logger.debug(
                f"Unable to process Jira Worklog {webhook_event} event. The associated Flow "
                f"Production Tracking Task is not flagged to be synced."
            )
            return False

        if webhook_event == "worklog_deleted":
            if len(sg_timelogs) == 0:
                self._logger.debug(
                    f"Unable to process Jira Worklog {webhook_event} event. Couldn't find any TimeLog "
                    f"in Flow Production Tracking with Jira key {sg_jira_key}"
                )
                return False
            self._logger.info(
                f"Deleting Flow Production Tracking TimeLog ({sg_timelogs[0]['id']})"
            )
            self._shotgun.delete("TimeLog", sg_timelogs[0]["id"])
            self._remove_sg_user_from_jira_worklog(jira_issue, jira_worklog["id"])

        else:

            # Because there are some limitations in the Jira API regarding the worklog assignation,
            # we need to store the PTR TimeLog user in a custom field to be able to keep a mapping
            # between the PTR Timelog assignee and the Jira Worklog assignee
            sg_user = self._get_sg_user_from_jira_worklog(
                jira_issue, jira_worklog["id"]
            )
            if not sg_user:
                sg_user = self.get_sg_user(jira_worklog["author"]["accountId"])

            worklog_started_date = datetime.datetime.strptime(
                jira_worklog["started"], self.__JIRA_DATE_FORMAT
            ).strftime(self.__SG_DATE_FORMAT)
            sg_data = {
                "description": jira_worklog.get("comment", "New JIRA Timelog"),
                "user": sg_user,
                "date": worklog_started_date,
                "duration": int(jira_worklog["timeSpentSeconds"] / 60),
                "entity": sg_tasks[0],
                "project": sg_tasks[0]["project"],
                SHOTGUN_JIRA_ID_FIELD: sg_jira_key,
            }

            # The TimeLog doesn't exist in Flow Production Tracking, create it
            if len(sg_timelogs) == 0:
                self._shotgun.create("TimeLog", sg_data)
                self._logger.info(
                    f"Adding TimeLog ({sg_jira_key}) to Flow Production Tracking"
                )

            # The TimeLog already exist in Flow Production Tracking, update it
            else:
                self._shotgun.update("TimeLog", sg_timelogs[0]["id"], sg_data)
                self._logger.info(
                    f"Flow Production Tracking Timelog ({sg_jira_key}) updated successfully."
                )

        return True

    def _sync_existing_timelog_and_worklog(self, sg_task):
        """
        Sync all the existing Flow Production Tracking timelogs to Jira and once it's done,
        then sync the remaining Jira worklogs in Flow Production Tracking to make sure
        they are all created in both places.

        :param sg_task: A Flow Production Tracking Task dictionary.
        :returns: `True` if any update happened, `False` otherwise.
        """

        updated = False

        # start by syncing the PTR timelogs to Jira
        sg_task = self._shotgun.consolidate_entity(sg_task, fields=self._sg_task_fields)

        # get all the timelogs linked to the task
        sg_timelogs = self._shotgun.find(
            "TimeLog", [["entity", "is", sg_task]], self._sg_timelog_fields
        )
        self._logger.debug(
            f"Retrieved Flow Production Tracking TimeLogs {sg_timelogs} linked to Task {sg_task}"
        )

        # add them to Jira
        for sg_timelog in sg_timelogs:
            if self._add_timelog_to_jira(sg_timelog):
                updated = True

        # then, sync the Jira worklogs to Flow Production Tracking
        # we need to query again all the timelogs to be sure we have the updated Jira keys
        sg_timelogs = self._shotgun.find(
            "TimeLog", [["entity", "is", sg_task]], self._sg_timelog_fields
        )
        existing_timelog_ids = [t[SHOTGUN_JIRA_ID_FIELD] for t in sg_timelogs]
        jira_issue = self.get_jira_issue(sg_task[SHOTGUN_JIRA_ID_FIELD])
        for jira_worklog in self._jira.worklogs(sg_task[SHOTGUN_JIRA_ID_FIELD]):

            sg_jira_key = "%s/%s" % (sg_task[SHOTGUN_JIRA_ID_FIELD], jira_worklog.id)
            if sg_jira_key in existing_timelog_ids:
                continue

            sg_user = self._get_sg_user_from_jira_worklog(jira_issue, jira_worklog.id)
            if not sg_user:
                sg_user = self.get_sg_user(jira_worklog.author.accountId)

            worklog_started_date = datetime.datetime.strptime(
                jira_worklog.started, self.__JIRA_DATE_FORMAT
            ).strftime(self.__SG_DATE_FORMAT)
            sg_data = {
                "description": jira_worklog.comment,
                "user": sg_user,
                "date": worklog_started_date,
                "duration": int(jira_worklog.timeSpentSeconds / 60),
                "entity": sg_task,
                "project": sg_task["project"],
                SHOTGUN_JIRA_ID_FIELD: sg_jira_key,
            }
            self._shotgun.create("TimeLog", sg_data)
            self._logger.info(
                f"Adding TimeLog ({sg_jira_key}) to Flow Production Tracking"
            )

            updated = True

        return updated

    def _add_timelog_to_jira(self, sg_timelog):
        """
        Add a Flow Production TimeLog to Jira

        :param sg_timelog: An PTR TimeLog dictionary.
        :returns: `True` if any update happened, `False` otherwise.
        """

        jira_issue_key, jira_worklog_id = self._parse_timelog_jira_key(sg_timelog)

        # the worklog already exists in Jira, only update its content
        if jira_issue_key and jira_worklog_id:
            return self._sync_timelog_content_to_jira(sg_timelog)

        # we need to create the worklog in Jira
        else:

            sg_task = self._shotgun.consolidate_entity(
                sg_timelog["entity"], fields=self._sg_task_fields
            )

            # get the Jira project linked to the current project
            jira_project_key = sg_task["project.Project.%s" % SHOTGUN_JIRA_ID_FIELD]
            if not jira_project_key:
                self._logger.debug(
                    f"Unable to find Jira Project ID for PTR Task {sg_task}"
                )
                return False
            jira_project = self.get_jira_project(jira_project_key)
            if not jira_project:
                self._logger.debug(
                    f"Unable to find a Jira Project {jira_project_key} for PTR Project {sg_task['project']}"
                )
                return False

            # get the Jira issue linked to the SG Task
            jira_issue = self.get_jira_issue(sg_task[SHOTGUN_JIRA_ID_FIELD])
            if not jira_issue:
                self._logger.debug(
                    f"Unable to find Jira Issue {sg_task[SHOTGUN_JIRA_ID_FIELD]} for PTR Task {sg_task}"
                )
                return False

            # get the Jira user
            jira_user = None
            if sg_timelog.get("user"):
                sg_user = self._shotgun.consolidate_entity(sg_timelog["user"])
                if sg_user and sg_user.get("email"):
                    jira_user = self.get_jira_user(sg_user["email"], jira_project)

            self._logger.info(
                f"Flow Production Tracking TimeLog ({sg_timelog['id']}) added. Adding as a new "
                f"worklog on Jira Issue {jira_issue.key}"
            )
            started_date = None
            if sg_timelog.get("date"):
                started_date = datetime.datetime.strptime(
                    sg_timelog["date"], self.__SG_DATE_FORMAT
                )

            jira_worklog = self._jira.add_worklog(
                jira_issue,
                timeSpentSeconds=sg_timelog["duration"] * 60,
                comment=sg_timelog["description"],
                started=started_date,
                user=list(jira_user.values())[0] if jira_user else "",
            )
            jira_issue_key = jira_issue.key
            jira_worklog_id = jira_worklog.id

            # Due to Jira API limitation, for now it is not possible to specify the WorkLog user
            # even if the argument exists in the function, it is not working properly
            # this is why we are storing the username into a custom field to keep a track on it
            if sg_timelog.get("user"):
                self._add_sg_user_to_jira_worklog(
                    jira_issue, jira_worklog_id, sg_timelog.get("user")
                )

            if jira_issue_key and jira_worklog_id:

                timelog_key = "%s/%s" % (jira_issue_key, jira_worklog_id)
                self._logger.info(
                    f"Updating PTR TimeLog ({sg_timelog['id']}) with Jira worklog key {timelog_key}"
                )
                self._shotgun.update(
                    sg_timelog["type"],
                    sg_timelog["id"],
                    {SHOTGUN_JIRA_ID_FIELD: timelog_key},
                )

                return True

        return False

    def _remove_timelog_from_jira(self, sg_timelog, update_sg=True):
        """
        Remove a TimeLog from Jira

        :param sg_timelog: An PTR TimeLog dictionary.
        :param update_sg: Boolean to indicate if we want to update Flow Production Tracking after the deletion
        :returns: `True` if any update happened, `False` otherwise.
        """

        jira_issue_key, jira_worklog_id = self._parse_timelog_jira_key(sg_timelog)

        if not jira_issue_key or not jira_worklog_id:
            self._logger.debug(
                f"Couldn't remove Timelog from Jira: missing JIRA information "
                f"(issue key {jira_issue_key} -  worklog id {jira_worklog_id})"
            )
            return False

        jira_issue = self.get_jira_issue(jira_issue_key)
        if not jira_issue:
            self._logger.debug(
                f"Couldn't remove Timelog from Jira: missing JIRA issue (issue key {jira_issue_key})"
            )
            return False

        jira_worklog = self._get_jira_worklog(jira_issue_key, jira_worklog_id)
        if not jira_worklog:
            self._logger.debug(
                "Couldn't remove Timelog from Jira: couldn't get associated JIRA Worklog"
            )
            return False

        # delete the JIRA worklog
        jira_worklog.delete()

        # remove the timelog entry from the Jira custom field
        # this entry was used to track the timelog user
        self._remove_sg_user_from_jira_worklog(jira_issue, jira_worklog_id)

        if update_sg:
            self._shotgun.update(
                sg_timelog["type"],
                sg_timelog["id"],
                {
                    SHOTGUN_JIRA_ID_FIELD: "",
                },
            )

        return True

    def _parse_timelog_jira_key(self, sg_timelog):
        """
        Parse the Jira key value set in the given PTR TimeLog and return the Jira
        Issue key and the Jira Worklog id it refers to, if it is not empty.

        :returns: A tuple with a Jira Issue key and a Jira worklog id, or
                  `None, None`.
        :raises ValueError: if the Jira key is invalid.
        """
        if not sg_timelog[SHOTGUN_JIRA_ID_FIELD]:
            return None, None
        parts = sg_timelog[SHOTGUN_JIRA_ID_FIELD].split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(
                "Invalid Jira worklog id %s, it must be in the format "
                "'<jira issue key>/<jira worklog id>'"
                % (sg_timelog[SHOTGUN_JIRA_ID_FIELD])
            )
        return parts[0], parts[1]

    def _sync_timelog_content_to_jira(self, sg_timelog):
        """
        Synchronize a TimeLog content to Jira

        :param sg_timelog: A Flow Production Tracking TimeLog dictionary.
        :returns: `True` if any update happened, `False` otherwise.
        """

        jira_issue_key, jira_worklog_id = self._parse_timelog_jira_key(sg_timelog)

        if not jira_issue_key or not jira_worklog_id:
            self._logger.debug(
                "Couldn't sync Timelog content to Jira: missing JIRA information"
            )
            return False

        # get the Jira project linked to the current project
        jira_project_key = sg_timelog["project.Project.%s" % SHOTGUN_JIRA_ID_FIELD]
        if not jira_project_key:
            self._logger.debug(
                f"Couldn't sync timelog content: unable to find Jira Project ID for Timelog {sg_timelog}"
            )
            return False
        jira_project = self.get_jira_project(jira_project_key)
        if not jira_project:
            self._logger.debug(
                f"Couldn't sync timelog content: unable to find a Jira Project {jira_project_key} for "
                f"PTR Project {sg_timelog['project']}"
            )
            return False

        # get the Jira issue
        jira_issue = self.get_jira_issue(jira_issue_key)
        if not jira_issue:
            self._logger.debug(
                f"Couldn't sync timelog content: unable to find Jira Issue {jira_issue_key}"
            )
            return False

        # get the Jira user
        jira_user = None
        if sg_timelog.get("user"):
            sg_user = self._shotgun.consolidate_entity(sg_timelog["user"])
            if sg_user and sg_user.get("email"):
                jira_user = self.get_jira_user(sg_user["email"], jira_project)

        jira_worklog = self._get_jira_worklog(jira_issue_key, jira_worklog_id)
        if jira_worklog:
            self._logger.debug(
                f"Flow Production Tracking TimeLog ({sg_timelog['id']}) updated. "
                f"Syncing to Jira Issue {jira_issue_key} Worklog {jira_worklog}"
            )
            # we need to format the started date
            started_date = None
            if sg_timelog.get("date"):
                jira_formatted_date = self.__JIRA_DATE_FORMAT.replace("%f", "000")
                jira_formatted_date = jira_formatted_date.replace("%z", "+0000")
                started_date = datetime.datetime.strptime(
                    sg_timelog["date"], self.__SG_DATE_FORMAT
                ).strftime(jira_formatted_date)

            jira_worklog.update(
                timeSpentSeconds=sg_timelog["duration"] * 60,
                comment=sg_timelog["description"],
                started=started_date,
                user=list(jira_user.values())[0] if jira_user else "",
            )

            if sg_timelog.get("user"):
                self._add_sg_user_to_jira_worklog(
                    jira_issue, jira_worklog.id, sg_timelog.get("user")
                )

            return True

        return False

    def _get_jira_worklog(self, jira_issue_key, jira_worklog_id):
        """
        Retrieve the Jira worklog with the given id attached to the given Issue.

        .. note:: Jira worklogs can't live without being attached to an Issue,
                  so we use a "<Issue key>/<Worklog id>" key to reference a
                  particular comment.

        :param str jira_issue_key: A Jira Issue key.
        :param str jira_worklog_id: A Jira Worklog id.
        :returns: A :class:`jira.Worklog` instance or None.
        """
        jira_worklog = None
        try:
            jira_worklog = self._jira.worklog(jira_issue_key, jira_worklog_id)
        except JIRAError as e:
            # Jira raises a 404 error if it can't find the Worklog: catch the
            # error and keep the None value
            if e.status_code == 404:
                pass
            else:
                raise
        return jira_worklog

    def _add_sg_user_to_jira_worklog(self, jira_issue, jira_worklog_id, sg_user):
        """
        Helper method to store the Flow Production Tracking Timelog assignee into Jira.
        We need to do this because of the Jira api limitation where it is impossible to set the worklog user.

        :param jira_issue: The Jira issue the worklog is tied to.
        :param jira_worklog_id: Id of the Jira worklog.
        :param sg_user: A Flow Production Tracking User dictionary
        """

        if not self.__jira_sg_timelog_field:
            self._logger.debug(
                f"Couldn't set PTR TimeLog assignee: missing Jira field {self.__JIRA_SHOTGUN_TIMELOG_FIELD}"
            )
            return

        timelog_data = jira_issue.get_field(self.__jira_sg_timelog_field)
        timelog_data = json.loads(timelog_data) if timelog_data else {}

        timelog_data.setdefault(jira_worklog_id, {})["user"] = sg_user

        jira_issue.update(
            fields={self.__jira_sg_timelog_field: json.dumps(timelog_data)}
        )

    def _remove_sg_user_from_jira_worklog(self, jira_issue, jira_worklog_id):
        """
        Helper method to remove an PTR Timelog assignee from the Jira custom field used to store them.

        :param jira_issue: The Jira issue the worklog is tied to.
        :param jira_worklog_id: Id of the Jira worklog.
        """

        if not self.__jira_sg_timelog_field:
            self._logger.debug(
                f"Couldn't remove PTR TimeLog assignee: missing Jira field {self.__JIRA_SHOTGUN_TIMELOG_FIELD}"
            )
            return

        timelog_data = jira_issue.get_field(self.__jira_sg_timelog_field)
        timelog_data = json.loads(timelog_data) if timelog_data else {}

        if jira_worklog_id in timelog_data:
            del timelog_data[jira_worklog_id]
            jira_issue.update(
                fields={self.__jira_sg_timelog_field: json.dumps(timelog_data)}
            )

    def _get_sg_user_from_jira_worklog(self, jira_issue, jira_worklog_id):
        """
        Helper method to get the Flow Production Tracking user assigned to the Jira worklog.

        :param jira_issue: The Jira issue the worklog is tied to.
        :param jira_worklog_id: Id of the Jira worklog.
        :returns: The Flow Production Tracking User as dictionary
        """

        if not self.__jira_sg_timelog_field:
            self._logger.debug(
                f"Couldn't get PTR TimeLog assignee: missing Jira field {self.__JIRA_SHOTGUN_TIMELOG_FIELD}"
            )
            return None

        timelog_data = jira_issue.get_field(self.__jira_sg_timelog_field)
        timelog_data = json.loads(timelog_data) if timelog_data else {}

        return timelog_data.get(jira_worklog_id, {}).get("user")
