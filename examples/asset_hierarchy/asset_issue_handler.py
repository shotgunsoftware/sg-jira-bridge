# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from sg_jira.constants import (ASSET_FIELDS_MAPPING,
                               ASSET_ISSUE_STATUS_MAPPING,
                               ISSUE_FIELDS_MAPPING, JIRA_PARENT_LINK_TYPE,
                               SHOTGUN_JIRA_ID_FIELD, SHOTGUN_JIRA_URL_FIELD,
                               SHOTGUN_SYNC_IN_JIRA_FIELD)
from sg_jira.errors import InvalidShotgunValue
from sg_jira.handlers import EntityIssueHandler


class AssetIssueHandler(EntityIssueHandler):
    """
    A handler which syncs a Flow Production Tracking Asset as a Jira Issue.
    Need to update process_shotgun_event to add create Story functions.
    """

    # Define the mapping between Shotgun Asset fields and Jira Issue fields
    __ASSET_FIELDS_MAPPING = ASSET_FIELDS_MAPPING

    # The type of Issue link to use when linking a Task Issue to the Issue
    # representing the Asset.
    __JIRA_PARENT_LINK_TYPE = JIRA_PARENT_LINK_TYPE

    # Define the mapping between Jira Issue fields and Shotgun Asset fields
    # if the Shotgun target is None, it means the target field is not settable
    # directly.
    __ISSUE_FIELDS_MAPPING = ISSUE_FIELDS_MAPPING

    @property
    def _shotgun_asset_fields(self):
        """
        Return the list of fields to ask for when retrieving an Asset from
        Flow Production Tracking.
        """
        return [
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
            SHOTGUN_JIRA_ID_FIELD,
        ] + self._supported_shotgun_fields_for_shotgun_event()

    @property
    def _sg_jira_status_mapping(self):
        """
        Return a dictionary where keys are Flow Production Tracking status short codes and values
        are Jira Issue status names.
        """
        return ASSET_ISSUE_STATUS_MAPPING

    @property
    def _supported_shotgun_fields_for_jira_event(self):
        """
        Return the list of fields this handler can process for a Jira event.

        :returns: A list of strings.
        """
        # By convention we might have `None` as values in our mapping dictionary
        # meaning that we handle a specific Jira field but there is not a direct
        # mapping to a Shotgun field and a special logic must be implemented
        # and called to perform the update to Shotgun.
        return [field for field in self.__ISSUE_FIELDS_MAPPING.values() if field]

    def _supported_shotgun_fields_for_shotgun_event(self):
        """
        Return the list of Flow Production Tracking fields that this handler can process for a
        Flow Production Tracking to Jira event.
        """
        return list(self.__ASSET_FIELDS_MAPPING.keys())

    def _get_jira_issue_field_for_shotgun_field(
        self, shotgun_entity_type, shotgun_field
    ):
        """
        Returns the Jira Issue field id to use to sync the given Flow Production Tracking Entity
        type field.

        :param str shotgun_entity_type: A Flow Production Tracking Entity type, e.g. 'Task'.
        :param str shotgun_field: A Flow Production Tracking Entity field name, e.g. 'sg_status_list'.
        :returns: A string or ``None``.
        """
        if shotgun_entity_type != "Asset":
            return None
        return self.__ASSET_FIELDS_MAPPING.get(shotgun_field)

    def _get_shotgun_entity_field_for_issue_field(self, jira_field_id):
        """
        Returns the Flow Production Tracking field name to use to sync the given Jira Issue field.

        :param str jira_field_id: A Jira Issue field id, e.g. 'summary'.
        :returns: A string or ``None``.
        """
        return self.__ISSUE_FIELDS_MAPPING.get(jira_field_id)

    def _sync_asset_to_jira(self, shotgun_asset, event_meta=None):
        """
        Update an existing Jira Issue from the Flow Production Tracking Asset fields.

        :param shotgun_asset: A Flow Production Tracking Asset dictionary.
        :param event_meta: A Flow Production Tracking Event meta data dictionary or ``None``.
        :returns: ``True`` if a Jira Issue was updated, ``False`` otherwise.
        """
        jira_issue_key = shotgun_asset[SHOTGUN_JIRA_ID_FIELD]
        if not jira_issue_key:
            return False

        jira_issue = self._get_jira_issue_and_validate(jira_issue_key, shotgun_asset)
        if not jira_issue:
            return False

        # Process all supported fields if no event meta data was provided.
        if not event_meta:
            return self._sync_shotgun_fields_to_jira(shotgun_asset, jira_issue)

        sg_field = event_meta["attribute_name"]
        try:
            jira_field, jira_value = self._get_jira_issue_field_sync_value(
                jira_issue.fields.project,
                jira_issue,
                shotgun_asset["type"],
                sg_field,
                event_meta.get("added"),
                event_meta.get("removed"),
                event_meta.get("new_value"),
            )
        except InvalidShotgunValue as e:
            self._logger.warning(
                "Unable to update Jira %s %s for event %s: %s"
                % (
                    jira_issue.fields.issuetype.name,
                    jira_issue.key,
                    event_meta,
                    e,
                )
            )
            self._logger.debug("%s" % e, exc_info=True)
            return False

        if jira_field:
            self._logger.debug(
                "Updating Jira %s %s field with %s"
                % (jira_issue, jira_field, jira_value)
            )
            jira_issue.update(fields={jira_field: jira_value})
            return True

        # Special cases not handled by a direct update
        if sg_field == "sg_status_list":
            shotgun_status = event_meta["new_value"]
            return self._sync_shotgun_status_to_jira(
                jira_issue,
                shotgun_status,
                "Updated from Flow Production Tracking %s(%d) moving to %s"
                % (shotgun_asset["type"], shotgun_asset["id"], shotgun_status),
            )

        return False

    def _get_jira_issue_link(self, from_issue, to_issue_key):
        """
        Retrieve an existing link between the given Jira Issue and another Issue
        with the given key.

        :param from_issue: A :class:`jira.Issue` instance.
        :param str to_issue_key: An Issue key.
        :returns: An Issue link or ``None``.
        """
        for issue_link in from_issue.fields.issuelinks:
            # Depending link directions we either get "inwardIssue" or "outwardIssue"
            # populated.
            if issue_link.raw.get("inwardIssue"):
                if issue_link.inwardIssue.key == to_issue_key:
                    # Note: we don't check the Issue Link type and return any link
                    # which is n the right direction.
                    return issue_link
        return None

    def _sync_asset_tasks_change_to_jira(self, shotgun_asset, added, removed):
        """
        Update Jira with tasks changes for the given Flow Production Tracking Asset.

        :param shotgun_asset: A Flow Production Tracking Asset dictionary.
        :param added: A list of Flow Production Tracking Task dictionaries which were added to
                      the given Asset.
        :param removed: A list of Flow Production Tracking Task dictionaries which were removed from
                        the given Asset.
        :returns: ``True`` if the given changes could be processed sucessfully,
                  ``False`` otherwise.
        """

        jira_issue_key = shotgun_asset[SHOTGUN_JIRA_ID_FIELD]
        jira_issue = None
        if jira_issue_key:
            # Retrieve the Issue if we should have one
            jira_issue = self.get_jira_issue(jira_issue_key)
            if not jira_issue:
                self._logger.warning(
                    "Unable to find Jira Issue %s for Flow Production Tracking Asset %s"
                    % (jira_issue_key, shotgun_asset)
                )
                # Better to stop processing.
                return False

        updated = False
        if jira_issue and removed:
            # Check if we should update dependencies because it was attached to
            # a synced Task which has been removed.
            sg_tasks = self._shotgun.find(
                "Task",
                [
                    ["id", "in", [x["id"] for x in removed]],
                    [SHOTGUN_JIRA_ID_FIELD, "is_not", None],
                    [SHOTGUN_SYNC_IN_JIRA_FIELD, "is", True],
                ],
                ["content", SHOTGUN_JIRA_ID_FIELD],
            )
            to_delete = []
            for sg_task in sg_tasks:
                issue_link = self._get_jira_issue_link(
                    jira_issue, sg_task[SHOTGUN_JIRA_ID_FIELD]
                )
                if issue_link:
                    self._logger.debug(
                        "Found a Jira link between %s and %s to delete"
                        % (jira_issue.key, sg_task[SHOTGUN_JIRA_ID_FIELD])
                    )
                    to_delete.append(issue_link)
                else:
                    self._logger.debug(
                        "Didn't find a Jira link between %s and %s to delete"
                        % (jira_issue.key, sg_task[SHOTGUN_JIRA_ID_FIELD])
                    )

            # Delete the links, if any
            for issue_link in to_delete:
                self._logger.info("Deleting Jira link %s" % (issue_link))
                self._jira.delete_issue_link(issue_link.id)
                updated = True

        if added:
            # Collect the list of Tasks which are linked to Jira Issues
            sg_tasks = self._shotgun.find(
                "Task",
                [
                    ["id", "in", [x["id"] for x in added]],
                    [SHOTGUN_JIRA_ID_FIELD, "is_not", None],
                    [SHOTGUN_SYNC_IN_JIRA_FIELD, "is", True],
                ],
                ["content", SHOTGUN_JIRA_ID_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD],
            )
            if not sg_tasks:
                # Nothing to do
                return False

            if not jira_issue:
                # Check if the Project is linked to a Jira Project
                jira_project_key = shotgun_asset[
                    "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD
                ]
                if not jira_project_key:
                    self._logger.debug(
                        "Skipping tasks change event for %s (%d) for Project %s "
                        "not linked to a Jira Project"
                        % (
                            shotgun_asset["type"],
                            shotgun_asset["id"],
                            shotgun_asset["project"],
                        )
                    )
                    return False

                jira_project = self.get_jira_project(jira_project_key)
                if not jira_project:
                    self._logger.warning(
                        "Unable to find Jira Project %s for Flow Production Tracking Project %s."
                        % (
                            jira_project_key,
                            shotgun_asset["project"],
                        )
                    )
                    return False

                # Time to create the Issue
                jira_issue = self._create_jira_issue_for_entity(
                    shotgun_asset,
                    jira_project,
                    self._issue_type,
                    summary=shotgun_asset["code"],
                    timetracking={
                        "originalEstimate": "0 m"  # Null estimate in the case it is mandatory
                    },
                )
                self._shotgun.update(
                    shotgun_asset["type"],
                    shotgun_asset["id"],
                    {
                        SHOTGUN_JIRA_ID_FIELD: jira_issue.key,
                        SHOTGUN_JIRA_URL_FIELD: {
                            "url": jira_issue.permalink(),
                            "name": "View in Jira",
                        },
                    },
                )
                updated = True

            for sg_task in sg_tasks:
                issue_link = self._get_jira_issue_link(
                    jira_issue, sg_task[SHOTGUN_JIRA_ID_FIELD]
                )

                if not issue_link:
                    self._logger.info(
                        "Linking Jira Issue %s to %s"
                        % (jira_issue.key, sg_task[SHOTGUN_JIRA_ID_FIELD])
                    )
                    self._jira.create_issue_link(
                        type=self.__JIRA_PARENT_LINK_TYPE,
                        # Note: depending on the link type, e.g. "blocks" or
                        # "is blocked", the inward and outward values might need
                        # to be swapped
                        inwardIssue=sg_task[SHOTGUN_JIRA_ID_FIELD],
                        outwardIssue=jira_issue.key,
                        comment={
                            "body": "Linking %s to %s"
                            % (
                                shotgun_asset["code"],
                                sg_task["content"],
                            ),
                        },
                    )
                    updated = True
                else:
                    self._logger.debug(
                        "Jira Issue %s is already linked to %s"
                        % (jira_issue.key, sg_task[SHOTGUN_JIRA_ID_FIELD])
                    )

        return updated

    def _sync_shotgun_fields_to_jira(
        self, sg_entity, jira_issue, exclude_shotgun_fields=None
    ):
        """
        Update the given Jira Issue with values from the given Flow Production Tracking Entity.

        An optional list of Flow Production Tracking fields can be provided to exclude them from
        the sync.

        :param sg_entity: A Flow Production Tracking Entity dictionary.
        :param jira_issue: A :class:`jira.Issue` instance.
        :param exclude_shotgun_fields: An optional list of Flow Production Tracking field names which
                                       shouldn't be synced.
        """

        if exclude_shotgun_fields is None:
            exclude_shotgun_fields = []

        issue_data = {}
        for sg_field, jira_field in self.__ASSET_FIELDS_MAPPING.items():
            if sg_field in exclude_shotgun_fields:
                continue

            if jira_field is None:
                # Special cases where a direct update is not possible.
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
                    "Unable to update Jira %s %s %s field from Flow Production Tracking value %s: %s"
                    % (
                        jira_issue.fields.issuetype.name,
                        jira_issue.key,
                        jira_field,
                        shotgun_value,
                        e,
                    )
                )
                self._logger.debug("%s" % e, exc_info=True)
        if issue_data:
            self._logger.debug(
                "Updating Jira %s %s with %s. Currently: %s"
                % (
                    jira_issue.fields.issuetype.name,
                    jira_issue.key,
                    issue_data,
                    jira_issue,
                )
            )
            jira_issue.update(fields=issue_data)

        # Sync status
        if "sg_status_list" not in exclude_shotgun_fields:
            self._sync_shotgun_status_to_jira(
                jira_issue,
                sg_entity["sg_status_list"],
                "Updated from Flow Production Tracking %s(%d) moving to %s"
                % (sg_entity["type"], sg_entity["id"], sg_entity["sg_status_list"]),
            )

    def _sync_shotgun_task_asset_to_jira(self, shotgun_task):
        """
        Sync the Asset attached to the given Flow Production Tracking Task to Jira.

        :param shotgun_task: A Flow Production Tracking Task dictionary.
        :returns: ``True`` if any update happened, ``False`` otherwise.
        """
        # Retrieve the Asset linked to the Task, if any
        shotgun_asset = self._shotgun.find_one(
            "Asset", [["tasks", "is", shotgun_task]], self._shotgun_asset_fields
        )
        # make sure we have a full entity needed with the injected "name" key, etc.
        shotgun_asset = self._shotgun.consolidate_entity(
            shotgun_asset, fields=self._shotgun_asset_fields
        )

        self._logger.debug(
            "Retrieved Asset %s linked to Task %s" % (shotgun_asset, shotgun_task)
        )

        if not shotgun_asset:
            return False

        updated = False
        res = self._sync_asset_tasks_change_to_jira(
            shotgun_asset, added=[shotgun_task], removed=[]
        )
        if res:
            updated = True
        if self._sync_asset_to_jira(shotgun_asset):
            updated = True

        return updated

    def setup(self):
        """
        Check the Jira and Flow Production Tracking site, ensure that the sync can safely happen.
        This can be used as well to cache any value which is slow to retrieve.
        """
        self._shotgun.assert_field(
            "Asset", SHOTGUN_JIRA_ID_FIELD, "text", check_unique=True
        )
        self._shotgun.assert_field("Asset", SHOTGUN_JIRA_URL_FIELD, "url")

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Flow Production Tracking Entity.

        :returns: ``True`` if the event is accepted for processing, ``False`` otherwise.
        """
        # We only accept Assets
        if entity_type != "Asset":
            return False

        meta = event["meta"]
        field = meta["attribute_name"]

        if field not in self._supported_shotgun_fields_for_shotgun_event():
            self._logger.debug(
                "Rejecting Flow Production Tracking event with unsupported Flow Production Tracking field %s: %s"
                % (field, event)
            )
            return False

        return True

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Flow Production Tracking event for the given Flow Production Tracking Entity

        :param str entity_type: The Flow Production Tracking Entity type to sync.
        :param int entity_id: The id of the Flow Production Tracking Entity to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event was successfully processed, False if the
                  sync didn't happen for any reason.
        """
        meta = event["meta"]
        shotgun_field = meta["attribute_name"]

        if shotgun_field == SHOTGUN_SYNC_IN_JIRA_FIELD:
            # Note: in this case the Entity is a Task.
            return self._sync_shotgun_task_asset_to_jira(
                {"type": entity_type, "id": entity_id}
            )

        asset_fields = [
            "project",
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
            SHOTGUN_JIRA_ID_FIELD,
            SHOTGUN_SYNC_IN_JIRA_FIELD,
        ] + self._supported_shotgun_fields_for_shotgun_event()

        sg_entity = self._shotgun.consolidate_entity(
            {"type": entity_type, "id": entity_id}, fields=asset_fields
        )
        if not sg_entity:
            self._logger.warning(
                "Unable to find Flow Production Tracking %s (%s)."
                % (entity_type, entity_id)
            )
            return False

        # Explicit sync: check if the "Sync in Jira" checkbox is on.
        if not sg_entity[SHOTGUN_SYNC_IN_JIRA_FIELD]:
            self._logger.debug(
                "Not syncing Flow Production Tracking entity %s. 'Sync in Jira' is off"
                % sg_entity,
            )
            return False

        # Check if the Project is linked to a Jira Project
        jira_project_key = sg_entity["project.Project.%s" % SHOTGUN_JIRA_ID_FIELD]
        if not jira_project_key:
            self._logger.debug(
                "Skipping Flow Production Tracking event for %s (%d). Entity's Project %s "
                "is not linked to a Jira Project. Event: %s"
                % (
                    entity_type,
                    entity_id,
                    sg_entity["project"],
                    event,
                )
            )
            return False
        jira_project = self.get_jira_project(jira_project_key)
        if not jira_project:
            self._logger.warning(
                "Unable to find a Jira Project %s for Flow Production Tracking Project %s"
                % (
                    jira_project_key,
                    sg_entity["project"],
                )
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
                "Rejecting Flow Production Tracking event for %s.%s field update during "
                "create. Issue was already created in Jira: %s"
                % (sg_entity["type"], shotgun_field, event)
            )
            return False

        # Add for creating JIRA story if story doesn't exist
        jira_issue = None
        if sg_entity[SHOTGUN_JIRA_ID_FIELD]:
            # Retrieve the Jira Issue
            jira_issue = self._get_jira_issue_and_validate(
                sg_entity[SHOTGUN_JIRA_ID_FIELD], sg_entity
            )
            if not jira_issue:
                return False

        # Create it if needed
        self._logger.debug("No Story found. Creating ...")

        if not jira_issue:
            jira_issue = self._create_jira_issue_for_entity(
                sg_entity,
                jira_project,
                self._issue_type,
                summary=sg_entity["code"],
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
                sg_entity,
                jira_issue,
            )
            return True

        # Otherwise, handle the attribute change
        self._logger.info(
            "Syncing Flow Production Tracking %s.%s (%d) to Jira %s %s"
            % (
                entity_type,
                sg_field,
                entity_id,
                jira_issue.fields.issuetype.name,
                jira_issue.key,
            )
        )
        self._logger.debug("Flow Production Tracking event: %s" % event)

        # Update existing synced Issue (if any) Issue dependencies
        # Note: deleting a Task does not seem to trigger an Asset.tasks change?
        if shotgun_field == "tasks":
            return self._sync_asset_tasks_change_to_jira(
                sg_entity,
                meta["added"],
                meta["removed"],
            )

        # Update the Jira Issue itself
        return self._sync_asset_to_jira(sg_entity, meta)
