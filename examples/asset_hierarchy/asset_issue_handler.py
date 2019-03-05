# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from sg_jira.handlers import EntityIssueHandler
from sg_jira.constants import SHOTGUN_JIRA_ID_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD
from sg_jira.errors import InvalidShotgunValue


class AssetIssueHandler(EntityIssueHandler):
    """
    A handler which syncs a Shotgun Asset as a Jira Issue
    """

    # Define the mapping between Shotgun Asset fields and Jira Issue fields
    __ASSET_FIELDS_MAPPING = {
        "code": "summary",
        "description": "description",
        "tags": "labels",
        "created_by": "reporter",
        "tasks": None,
        "sg_status_list": None,
    }

    # The type of Issue link to use when linking a Task Issue to the Issue
    # representing the Asset.
    __JIRA_PARENT_LINK_TYPE = "is blocked by"

    # Define the mapping between Jira Issue fields and Shotgun Asset fields
    # if the Shotgun target is None, it means the target field is not settable
    # directly.
    __ISSUE_FIELDS_MAPPING = {
        "summary": "code",
        "description": "description",
        "status": "sg_status_list",
        "labels": "tags",
    }

    @property
    def _shotgun_asset_fields(self):
        return [
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
            SHOTGUN_JIRA_ID_FIELD,
        ] + self._supported_shotgun_fields_for_shotgun_event()

    @property
    def _sg_jira_status_mapping(self):
        """
        Return a dictionary where keys are Shotgun status short codes and values
        Jira Issue status names.
        """
        return {
            "ip": "In Progress",
            "fin": "Done",
            "res": "Done",
            "rdy": "Selected for Development",  # Used to be "To Do" ?
            "wtg": "Selected for Development",
            "hld": "Backlog",
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
        return [
            field for field in self.__ISSUE_FIELDS_MAPPING.itervalues() if field
        ]

    def _supported_shotgun_fields_for_shotgun_event(self):
        """
        Return the list of Shotgun fields that this handler can process for a
        Shotgun to Jira event.
        """
        return self.__ASSET_FIELDS_MAPPING.keys()

    def _get_jira_issue_field_for_shotgun_field(self, shotgun_entity_type, shotgun_field):
        """
        Returns the Jira Issue field id to use to sync the given Shotgun Entity
        type field.

        :param str shotgun_entity_type: A Shotgun Entity type, e.g. 'Task'.
        :param str shotgun_field: A Shotgun Entity field name, e.g. 'sg_status_list'.
        :returns: A string or `None`.
        """
        if shotgun_entity_type != "Asset":
            return None
        return self.__ASSET_FIELDS_MAPPING.get(shotgun_field)

    def _get_shotgun_entity_field_for_issue_field(self, jira_field_id):
        """
        Returns the Shotgun field name to use to sync the given Jira Issue field.

        :param str jira_field_id: A Jira Issue field id, e.g. 'summary'.
        :returns: A string or `None`.
        """
        return self.__ISSUE_FIELDS_MAPPING.get(jira_field_id)

    def _sync_asset_to_jira(self, shotgun_asset, event_meta=None):
        """
        Update an existing Jira Issue from the Shotgun Asset fields.

        :param event_meta: A Shotgun Event meta data dictionary or `None`.
        :returns: `True` if a Jira Issue was updated, `False` otherwise.
        """
        jira_issue_key = shotgun_asset[SHOTGUN_JIRA_ID_FIELD]
        if not jira_issue_key:
            return False

        jira_issue = self.get_jira_issue(jira_issue_key)
        if not jira_issue:
            self._logger.warning(
                "Unable to retrieve a %s Issue" % jira_issue_key
            )
            # Better to stop processing.
            return False

        # Process all supported fields ff no event meta data was provied.
        if not event_meta:
            return self._sync_shotgun_fields_to_jira(
                shotgun_asset,
                jira_issue
            )

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
                "Unable to update Jira %s for event %s: %s" % (
                    jira_issue,
                    event_meta,
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

        # Special cases not handled by a direct update
        if sg_field == "sg_status_list":
            shotgun_status = event_meta["new_value"]
            return self._sync_shotgun_status_to_jira(
                jira_issue,
                shotgun_status,
                "Updated from Shotgun %s(%d) moving to %s" % (
                    shotgun_asset["type"],
                    shotgun_asset["id"],
                    shotgun_status
                )
            )

        return False

    def _get_jira_issue_link(self, from_issue, to_issue_key):
        """
        Retrieve an existing link between the given Jira Issue and another Issue
        with the given key.

        :param from_issue: A :class:`jira.resources.Issue` instance.
        :param str to_issue_key: An Issue key.
        :returns: An Issue link or `None`.
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
        Update Jira with tasks changes for the given Shotgun Asset.

        :param shotgun_asset: A Shotgun Asset dictionary.
        :param added: A list of Shotgun Task dictionaries which were added to
                      the given Asset.
        :param removed: A list of Shotgun Task dictionaries which were removed from
                        the given Asset.
        :returns: `True` if the given changes could be processed sucessfully,
                  `False` otherwise.
        """

        jira_issue_key = shotgun_asset[SHOTGUN_JIRA_ID_FIELD]
        jira_issue = None
        if jira_issue_key:
            # Retrieve the Issue if we should have one
            jira_issue = self.get_jira_issue(jira_issue_key)
            if not jira_issue:
                self._logger.warning(
                    "Unable to retrieve a %s Issue" % jira_issue_key
                )
                # Better to stop processing.
                return False

        updated = False
        if jira_issue and removed:
            # Check if we should update dependencies because it was attached to
            # a synced Task which has been removed.
            sg_tasks = self._shotgun.find(
                "Task", [
                    ["id", "in", [x["id"] for x in removed]],
                    [SHOTGUN_JIRA_ID_FIELD, "is_not", None],
                    [SHOTGUN_SYNC_IN_JIRA_FIELD, "is", True]
                ],
                ["content", SHOTGUN_JIRA_ID_FIELD]
            )
            to_delete = []
            for sg_task in sg_tasks:
                issue_link = self._get_jira_issue_link(
                    jira_issue,
                    sg_task[SHOTGUN_JIRA_ID_FIELD]
                )
                if issue_link:
                    self._logger.debug("Found a link between %s and %s to delete" % (
                        jira_issue.key,
                        sg_task[SHOTGUN_JIRA_ID_FIELD]
                    ))
                    to_delete.append(issue_link)
                else:
                    self._logger.debug("Didn't a find link between %s and %s to delete" % (
                        jira_issue.key,
                        sg_task[SHOTGUN_JIRA_ID_FIELD]
                    ))

            # Delete the links, if any
            for issue_link in to_delete:
                self._logger.info("Deleting link %s" % (
                    issue_link
                ))
                self._jira.delete_issue_link(issue_link.id)
                updated = True

        if added:
            # Collect the list of Tasks which are linked to Jira Issues
            sg_tasks = self._shotgun.find(
                "Task", [
                    ["id", "in", [x["id"] for x in added]],
                    [SHOTGUN_JIRA_ID_FIELD, "is_not", None],
                    [SHOTGUN_SYNC_IN_JIRA_FIELD, "is", True]
                ],
                ["content", SHOTGUN_JIRA_ID_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD]
            )
            if not sg_tasks:
                # Nothing to do
                return False

            if not jira_issue:
                # Check if the Project is linked to a Jira Project
                jira_project_key = shotgun_asset["project.Project.%s" % SHOTGUN_JIRA_ID_FIELD]
                if not jira_project_key:
                    self._logger.debug(
                        "Skipping tasks change event for %s(%d) for Project %s "
                        "not linked to a Jira Project" % (
                            shotgun_asset["type"],
                            shotgun_asset["id"],
                            shotgun_asset["project"],
                        )
                    )
                    return False

                jira_project = self.get_jira_project(jira_project_key)
                if not jira_project:
                    self._logger.warning(
                        "Unable to retrieve a Jira Project %s for Shotgun Project %s" % (
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
                    }
                )
                self._shotgun.update(
                    shotgun_asset["type"],
                    shotgun_asset["id"],
                    {SHOTGUN_JIRA_ID_FIELD: jira_issue.key}
                )
                updated = True

            for sg_task in sg_tasks:
                issue_link = self._get_jira_issue_link(
                    jira_issue,
                    sg_task[SHOTGUN_JIRA_ID_FIELD]
                )

                if not issue_link:
                    self._logger.info(
                        "Linking %s to %s" % (
                            jira_issue.key,
                            sg_task[SHOTGUN_JIRA_ID_FIELD]
                        )
                    )
                    self._jira.create_issue_link(
                        type=self.__JIRA_PARENT_LINK_TYPE,
                        # Note: depending on the link type, e.g. "blocks" or
                        # "is blocked", the inward and outward values might need
                        # to be swapped
                        inwardIssue=jira_issue.key,
                        outwardIssue=sg_task[SHOTGUN_JIRA_ID_FIELD],
                        comment={
                            "body": "Linking %s to %s" % (
                                shotgun_asset["code"],
                                sg_task["content"],
                            ),
                        }
                    )
                    updated = True
                else:
                    self._logger.debug(
                        "%s is already linked to %s" % (
                            jira_issue.key,
                            sg_task[SHOTGUN_JIRA_ID_FIELD]
                        )
                    )

        return updated

    def _sync_shotgun_fields_to_jira(self, sg_entity, jira_issue, exclude_shotgun_fields=None):
        """
        Update the given Jira Issue with values from the given Shotgun Entity.

        An optional list of Shotgun fields can be provided to exclude them from
        the sync.

        :param sg_entity: A Shotgun Entity dictionary.
        :param jira_issue: A :class:`jira.resources.Issue` instance.
        :param exclude_shotgun_fields: An optional list of Shotgun field names which
                                       shouldn't be synced.
        """

        if exclude_shotgun_fields is None:
            exclude_shotgun_fields = []

        issue_data = {}
        for sg_field, jira_field in self.__ASSET_FIELDS_MAPPING.iteritems():
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
                    new_value
                )
                if jira_field:
                    issue_data[jira_field] = jira_value
            except InvalidShotgunValue as e:
                self._logger.warning(
                    "Unable to update Jira %s %s field from Shotgun value %s" % (
                        jira_issue,
                        jira_field,
                        shotgun_value,
                    )
                )
                self._logger.debug("%s" % e, exc_info=True)
        if issue_data:
            self._logger.debug("Updating Jira %s with %s" % (
                jira_issue,
                issue_data
            ))
            jira_issue.update(fields=issue_data)

        # Sync status
        if "sg_status_list" not in exclude_shotgun_fields:
            self._sync_shotgun_status_to_jira(
                jira_issue,
                sg_entity["sg_status_list"],
                "Updated from Shotgun %s(%d) moving to %s" % (
                    sg_entity["type"],
                    sg_entity["id"],
                    sg_entity["sg_status_list"]
                )
            )

    def _sync_shotgun_task_asset_to_jira(self, shotgun_task):
        """
        Sync the Asset attached to the given Shotgun Task to Jira.

        :param shotgun_task: A Shotgun Task dictionary.
        :returns: `True` if any update happened, `False` otherwise.
        """
        shotgun_assets = self._shotgun.find(
            "Asset",
            [["tasks", "is", shotgun_task]],
            self._shotgun_asset_fields
        )
        self._logger.debug(
            "Retrieved Assets %s linked to Task %s" % (shotgun_assets, shotgun_task)
        )
        updated = False
        # Having a Task linked to multiple entities is rather unlikely to happen,
        # but we support it anyway.
        for shotgun_asset in shotgun_assets:
            res = self._sync_asset_tasks_change_to_jira(
                shotgun_asset,
                added=[shotgun_task],
                removed=[]
            )
            if res:
                updated = True
            if self._sync_asset_to_jira(shotgun_asset):
                updated = True

        return updated

    def setup(self):
        """
        Check the Jira and Shotgun site, ensure that the sync can safely happen.
        This can be used as well to cache any value which is slow to retrieve.
        """
        self._shotgun.assert_field("Asset", SHOTGUN_JIRA_ID_FIELD, "text")

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :returns: `True` if the event is accepted for processing, `False` otherwise.
        """
        # We only accept Assets
        if entity_type != "Asset":
            return False

        meta = event["meta"]
        field = meta["attribute_name"]

        if field not in self._supported_shotgun_fields_for_shotgun_event():
            self._logger.debug(
                "Rejecting event %s with unsupported field %s." % (
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
        ] + self._supported_shotgun_fields_for_shotgun_event()

        sg_entity = self._shotgun.consolidate_entity(
            {"type": entity_type, "id": entity_id},
            fields=asset_fields
        )
        if not sg_entity:
            self._logger.warning("Unable to retrieve a %s with id %d" % (
                entity_type,
                entity_id
            ))
            return False

        # Update existing synced Issue (if any) Issue dependencies
        # Note: deleting a Task does not seem to trigger an Asset.tasks change?
        if shotgun_field == "tasks":
            return self._sync_asset_tasks_change_to_jira(
                sg_entity,
                meta["added"],
                meta["removed"],
            )

        # Update the Jira Issue itself
        return self._sync_asset_to_jira(
            sg_entity,
            meta
        )
