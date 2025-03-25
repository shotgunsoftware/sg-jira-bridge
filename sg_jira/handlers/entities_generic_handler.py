# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
import datetime
import re

import jira

from sg_jira.constants import (JIRA_SHOTGUN_ID_FIELD, JIRA_SHOTGUN_TYPE_FIELD,
                               JIRA_SYNC_IN_FPTR_FIELD, SHOTGUN_JIRA_ID_FIELD,
                               SHOTGUN_JIRA_URL_FIELD,
                               SHOTGUN_SYNC_IN_JIRA_FIELD)
from .sync_handler import SyncHandler

# TODO:
#  - handle specific sg entities (list for example)/jira values in the `_sync_sg_fields_to_jira` method
#  - find a way to check if a field exist for a specific issue type when accepting SG event
#  - add a check for Jira Worklog fields existence
#  - ensure mandatory fields for Jira entity creation (eg: started + duration for TimeLogs)


class EntitiesGenericHandler(SyncHandler):
    """
    A handler that controls the bidirectional syncing of data between Flow Production Tracking and Jira.
    Unlike other handlers, it is designed to be a generic handler for all supported entity types.
    """

    # List of entities with a specific behavior
    # These entities couldn't be flagged as synced in Jira/FPTR (aka they don't have the "Sync in Jira"/"Sync in FPTR"
    # fields)
    # They will be synced automatically if they have been defined in the settings file, as soon as the entity they are
    # linked to is synced as well
    __ENTITIES_NOT_FLAGGED_AS_SYNCED = ["Note", "TimeLog"]

    # Define the FPTR field associated to the deletion action
    __SG_RETIREMENT_FIELD = "retirement_date"

    # Define the required FPTR fields for some specific entities not exposed entirely in the settings
    __NOTE_SG_FIELDS = ["subject", "content", "user", "tasks"]
    __TIMELOG_EXTRA_SG_FIELDS = ["user", "entity"]

    # Define the "fake" field used to map FPTR child entity with Jira entity
    # please, refer to the doc to see how this keyword can be used in the settings file
    __JIRA_CHILDREN_FIELD = "{{CHILDREN}}"

    def __init__(self, syncer, entity_mapping):
        """
        Instantiate a handler for the given syncer.
        :param syncer: A :class:`~sg_jira.Syncer` instance.
        :param entity_mapping: A list of entities to map.
            Each list entry is a python dictionary where the mapping between FPTR and Jira is done regarding the
            entity type, the fields to sync or the sync direction.
        """
        super(EntitiesGenericHandler, self).__init__(syncer)
        self.__entity_mapping = entity_mapping

    def setup(self):
        """
        Check the Jira and Flow Production Tracking site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """

        # Make sure the custom Jira field allowing the user to sync data from Jira to FPTR has been created
        # in Jira
        self.__jira_sync_in_fptr_field_id = self._jira.get_jira_issue_field_id(
            JIRA_SYNC_IN_FPTR_FIELD.lower()
        )
        if not self.__jira_sync_in_fptr_field_id:
            raise RuntimeError(
                "Missing required custom Jira field %s" % JIRA_SYNC_IN_FPTR_FIELD
            )

        for entity_mapping in self.__entity_mapping:

            # check that the FPTR entity has been set in the settings
            if "sg_entity" not in entity_mapping.keys():
                raise RuntimeError(
                    "Entity mapping does not contain sg_entity key, please check your settings."
                )
            self._shotgun.assert_entity(entity_mapping["sg_entity"])

            # for now, we don't support sync at project level
            if entity_mapping["sg_entity"] == "Project":
                raise RuntimeError("Syncing at Project level is not supported.")

            # make sure that the required FPTR fields has been created for the entity
            self._shotgun.assert_field(
                entity_mapping["sg_entity"],
                SHOTGUN_JIRA_ID_FIELD,
                "text",
                check_unique=True,
            )

            # for some entities, we need to add extra checks
            if entity_mapping["sg_entity"] not in self.__ENTITIES_NOT_FLAGGED_AS_SYNCED:

                if "jira_issue_type" not in entity_mapping.keys():
                    raise RuntimeError(
                        "Entity mapping does not contain jira_issue_type key, please check your settings."
                    )

                self._shotgun.assert_field(
                    entity_mapping["sg_entity"], SHOTGUN_SYNC_IN_JIRA_FIELD, "checkbox"
                )

            # as the Note mapping is done internally by the code, not using the setting fields mapping, we want to skip
            # some checks
            if entity_mapping["sg_entity"] not in ["Note"]:

                # check that the field mapping has been defined in the settings
                if "field_mapping" not in entity_mapping.keys():
                    raise RuntimeError(
                        "Entity mapping does not contain field_mapping key, please check your settings."
                    )

                for field_mapping in entity_mapping["field_mapping"]:

                    # check that the FPTR field has correctly been setup and exist in the FPTR schema
                    if "sg_field" not in field_mapping.keys():
                        raise RuntimeError(
                            "Field mapping does not contain sg_field key, please check your settings."
                        )
                    self._shotgun.assert_field(
                        entity_mapping["sg_entity"], field_mapping["sg_field"], None
                    )

                    # check that the Jira field exist
                    if "jira_field" not in field_mapping.keys():
                        raise RuntimeError(
                            "Field mapping does not contain jira_field key, please check your settings."
                        )
                    if (
                        entity_mapping["sg_entity"] != "TimeLog"
                        and field_mapping["jira_field"] != self.__JIRA_CHILDREN_FIELD
                    ):
                        self._jira.assert_field(field_mapping["jira_field"])

                    # special use case for the Jira assignee field
                    # it should only be mapped to a FPTR entity/multi-entity HumanUser field
                    if field_mapping["jira_field"] == "assignee":
                        sg_field_schema = self._shotgun.get_field_schema(
                            entity_mapping["sg_entity"], field_mapping["sg_field"]
                        )
                        data_type = sg_field_schema["data_type"]["value"]
                        if data_type not in ["multi_entity", "entity"]:
                            raise ValueError(
                                f"{data_type} field type is not valid for Flow Production Tracking "
                                f"{entity_mapping['sg_entity']}.{field_mapping['sg_field']} assignments. Expected "
                                "entity or multi_entity."
                            )
                        sg_valid_types = sg_field_schema["properties"]["valid_types"][
                            "value"
                        ]
                        if "HumanUser" not in sg_valid_types:
                            raise ValueError(
                                f"Flow Production Tracking {entity_mapping['sg_entity']}.{field_mapping['sg_field']} "
                                f"assignment field must accept HumanUser entities but only accepts {sg_valid_types}"
                            )

            # if the user has defined a status mapping, check that everything is correctly setup
            if "status_mapping" in entity_mapping.keys():
                if "sg_field" not in entity_mapping["status_mapping"].keys():
                    raise RuntimeError(
                        "Status mapping does not contain sg_field key, please check your settings."
                    )
                if "mapping" not in entity_mapping["status_mapping"].keys():
                    raise RuntimeError(
                        "Status mapping does not contain mapping key, please check your settings."
                    )
                # TODO: do we want to check that the status really exist in the two DBs
                # TODO: do we want to check that the FPTR field is actually a status field?

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Flow Production Tracking Entity.
        :returns: `True` if the event is accepted for processing, `False` otherwise.
        """

        self._logger.debug(f"Checking Flow Production Tracking event...\n {event}")

        # check that the entity linked to the event is supported by the bridge
        if entity_type not in self._supported_shotgun_entities_for_shotgun_event():
            self._logger.debug(
                f"Rejecting Flow Production Tracking event: unsupported FPTR entity type {entity_type}"
            )
            return False

        meta = event["meta"]
        field = meta["attribute_name"]
        sync_settings = self.__get_sg_entity_settings(entity_type)
        extra_sg_fields = [SHOTGUN_SYNC_IN_JIRA_FIELD]

        if sync_settings.get("sync_direction", "both_way") == "jira_to_sg":
            self._logger.debug(
                f"Rejecting Flow Production Tracking event: "
                f"the sync direction setting is configured to only sync from Jira to FPTR."
            )
            return False

        sync_deletion_direction = sync_settings.get("sync_deletion_direction", None)
        retired_only = False
        if field == self.__SG_RETIREMENT_FIELD:
            if entity_type not in self.__ENTITIES_NOT_FLAGGED_AS_SYNCED:
                self._logger.debug(
                    f"Rejecting Flow Production Tracking event: deletion is not supported for entity type {entity_type}"
                )
                return False
            elif sync_deletion_direction in [None, "jira_to_sg"]:
                self._logger.debug(
                    f"Rejecting Flow Production Tracking event: deletion is disabled for FPTR entity type {entity_type}"
                )
                return False
            else:
                extra_sg_fields.append(self.__SG_RETIREMENT_FIELD)
                retired_only = True

        # check that the field linked to the event is supported by the bridge
        if (
            field
            not in self._supported_shotgun_fields_for_shotgun_event(entity_type)
            + extra_sg_fields
        ):
            self._logger.debug(
                f"Rejecting Flow Production Tracking event: unsupported FPTR field {field}"
            )
            return False

        sg_entity = self._shotgun.find_one(
            entity_type,
            [["id", "is", entity_id]],
            self.__sg_get_entity_fields(entity_type),
            retired_only=retired_only,
        )
        if not sg_entity:
            self._logger.debug(
                f"Rejecting Flow Production Tracking event: unfounded FPTR entity {entity_type} ({entity_id})"
            )
            return False

        # for now, we only support project entities as we need to find the associated Jira project
        if not sg_entity.get(f"project.Project.{SHOTGUN_JIRA_ID_FIELD}"):
            self._logger.debug(
                f"Rejecting Flow Production Tracking event: {entity_type} ({entity_id}) doesn't belong to a FPTR"
                f" Project associated to a Jira Project."
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
        # event. If it exists with in_create, we know the entity has already
        # been created.
        if sg_entity[SHOTGUN_JIRA_ID_FIELD] and meta.get("in_create"):
            self._logger.debug(
                f"Rejecting Flow Production Tracking event: entity creation event was already handled."
            )
            return False

        # in case we are facing Note/TimeLog entity, we have some custom checks
        if entity_type in self.__ENTITIES_NOT_FLAGGED_AS_SYNCED:
            return self.__accept_shotgun_event_for_entities_not_flagged_as_synced(sg_entity, field, meta)

        return self.__accept_shotgun_event_for_entities_synced_as_issues(sg_entity, sync_settings["jira_issue_type"])

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Flow Production Tracking event for the given Flow Production Tracking Entity
        :param str entity_type: The PTR Entity type to sync.
        :param int entity_id: The id of the PTR Entity to sync.
        :param event: A dictionary with the event for the change.
        :returns: True if the event was successfully processed, False if the
                  sync didn't happen for any reason.
        """

        self._logger.debug(f"Processing Flow Production Tracking event...\n {event}")

        meta = event["meta"]
        sg_field = event["meta"]["attribute_name"]

        sg_entity = self._shotgun.consolidate_entity(
            {"type": entity_type, "id": entity_id},
            self.__sg_get_entity_fields(entity_type),
            retired_only=True if sg_field == self.__SG_RETIREMENT_FIELD else False,
        )

        if sg_field == self.__SG_RETIREMENT_FIELD:
            return self._delete_jira_entity(sg_entity)

        # if the entity already has an associated Jira ID, make sur to retrieve the associated Jira object
        jira_entity = None
        if sg_entity[SHOTGUN_JIRA_ID_FIELD]:
            jira_entity = self._get_jira_entity(sg_entity)
            if not jira_entity:
                return False

        jira_project_key = sg_entity[f"project.Project.{SHOTGUN_JIRA_ID_FIELD}"]
        jira_project = self.get_jira_project(jira_project_key)

        # special use case: when the entity linked to an existing TimeLog has been changed to a different entity,
        # we need to make sure we're removing the old worklog from Jira and create a new one
        # associated to the right Jira issue
        # same for the FPTR Notes/Jira Comments
        if (sg_entity["type"] == "TimeLog" and sg_field == "entity") or (
            sg_entity["type"] == "Note" and sg_field == "tasks"
        ):

            # delete the Jira entity in case it is not linked to a synced entity anymore
            # note about the meta formatting structure: if the modified field is a single entity field, the "old_value"
            # key will be used and will be a FPTR python dictionary
            # but if the modified field is a multi-entity field, the "removed" key will be used instead and its value
            # will be a list of FPTR python dictionary
            previous_entities = []
            if meta.get("old_value"):
                previous_entities.append(meta["old_value"])
            elif meta.get("removed"):
                previous_entities.extend(meta["removed"])
            for e in previous_entities:
                sg_linked_entity = self._shotgun.consolidate_entity(
                    e,
                    fields=[SHOTGUN_SYNC_IN_JIRA_FIELD, SHOTGUN_JIRA_ID_FIELD],
                )
                jira_issue_key, jira_entity_key = self.__parse_jira_key_from_sg_entity(
                    sg_entity
                )
                if (
                    sg_linked_entity[SHOTGUN_SYNC_IN_JIRA_FIELD]
                    and sg_linked_entity[SHOTGUN_JIRA_ID_FIELD] == jira_issue_key
                ):
                    # TODO: for now, we are deleting the Jira comments/worklogs without checking for the
                    #  sync_deletion_direction when a synced entity is unlinked
                    #  should we take this value into consideration instead instead of forcing the deletion in Jira?
                    self._delete_jira_entity(sg_entity, update_sg=True)

            # if a new entity is linked to the FPTR TimeLog/Comment, check if it has been flagged to be synced in Jira
            new_entities = []
            if meta.get("new_value"):
                new_entities.append(meta["new_value"])
            elif meta.get("added"):
                new_entities.extend(meta["added"])
            for e in new_entities:
                sg_linked_entity = self._shotgun.consolidate_entity(
                    e,
                    fields=[SHOTGUN_SYNC_IN_JIRA_FIELD],
                )
                if sg_linked_entity[SHOTGUN_SYNC_IN_JIRA_FIELD]:
                    jira_entity = None
                    continue

        # if the entity doesn't exist, create it and then sync all the fields
        if not jira_entity:
            jira_entity = self._create_jira_entity(sg_entity, jira_project)
            return self._sync_sg_fields_to_jira(sg_entity, jira_entity)

        # in case the sync checkbox has been triggered in FPTR, we want to perform a full sync of the entity
        if sg_field == SHOTGUN_SYNC_IN_JIRA_FIELD:
            return self._sync_sg_fields_to_jira(sg_entity, jira_entity)

        # otherwise, sync only the required field
        return self._sync_sg_fields_to_jira(sg_entity, jira_entity, field_name=sg_field)

    def accept_jira_event(self, resource_type, resource_id, event):
        """
        Accept or reject the given event for the given Jira resource.
        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event is accepted for processing, False otherwise.
        """

        sync_settings = None

        self._logger.debug(f"Checking Jira event...\n {event}")

        if resource_type.lower() != "issue":
            self._logger.debug(
                f"Rejecting Jira event for a {resource_type} Jira resource. Handler only "
                "accepts Issue resources."
            )
            return False

        webhook_event = event.get("webhookEvent")
        if (
            not webhook_event
            or webhook_event not in self._supported_jira_webhook_events()
        ):
            self._logger.debug(
                f"Rejecting Jira event with an unsupported webhook event '{webhook_event}'."
            )
            return False

        webhook_entity, webhook_action = self.__parse_jira_webhook_event(webhook_event)

        jira_entity = event.get(webhook_entity)
        if not jira_entity:
            self._logger.debug(f"Rejecting Jira event without a {webhook_entity}.")
            return False

        if webhook_entity in ["comment", "worklog"]:

            sg_entity_type = "Note" if webhook_entity == "comment" else "TimeLog"

            if webhook_action == "created":
                if (
                    jira_entity["author"]["accountId"]
                    == self._jira.myself()["accountId"]
                ):
                    self._logger.debug(
                        "Rejecting Jira event created by the bridge user."
                    )
                    return False

            elif webhook_action == "updated":
                if (
                    jira_entity["updateAuthor"]["accountId"]
                    == self._jira.myself()["accountId"]
                ):
                    self._logger.debug(
                        "Rejecting Jira event updated by the bridge user."
                    )
                    return False

            sync_settings = self.__get_sg_entity_settings(sg_entity_type)

            # make sure we can get the associated jira issue
            # comment and worklog payload are not formatted the same unfortunately...
            jira_issue_key = event.get("issue", {}).get("key")
            if not jira_issue_key:
                jira_issue_key = jira_entity.get("issueId")
            if not jira_issue_key:
                self._logger.debug("Rejecting Jira event without an associated issue.")
                return False
            jira_issue = self.get_jira_issue(jira_issue_key)

        else:

            changelog = event.get("changelog")
            if not changelog:
                self._logger.debug(f"Rejecting Jira event without a changelog.")
                return False

            jira_issue = self.get_jira_issue(jira_entity["id"])

        if not jira_issue:
            self._logger.debug("Rejecting Jira event: couldn't find Jira Issue.")
            return False

        # check that the issue type has been defined in the settings
        if (
            jira_issue.fields.issuetype.name
            not in self._supported_jira_issue_types_for_jira_event()
        ):
            self._logger.debug(
                f"Rejecting Jira event for unsupported issue type {jira_issue.fields.issuetype.name}"
            )
            return False

        if not sync_settings:
            sync_settings = self.__get_jira_issue_type_settings(
                jira_issue.fields.issuetype.name
            )
        if sync_settings.get("sync_direction", "both_way") == "sg_to_jira":
            self._logger.debug(
                f"Rejecting Jira event. The sync direction setting is configured to only sync from FPTR to Jira."
            )
            return False

        if webhook_action == "deleted":
            if sync_settings.get("sync_deletion_direction") in [None, "sg_to_jira"]:
                self._logger.debug(
                    f"Rejecting Jira event as deletion is disabled for Jira {webhook_entity}."
                )
                return False

        if not jira_issue.fields.project:
            self._logger.debug(f"Rejecting Jira event without a project.")
            return False

        # check that the Jira project is associated to a FPTR project
        sg_project = self._shotgun.find_one(
            "Project", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.fields.project.key]]
        )
        if not sg_project:
            self._logger.debug(
                f"Rejecting Jira event because the Jira Project {jira_issue.fields.project.key} doesn't have an associated "
                f"Flow Production Tracking project."
            )
            return False

        # check that the required Jira fields has been enabled for the current project and issue type
        required_fields = [JIRA_SYNC_IN_FPTR_FIELD]
        for rf in required_fields:
            jira_field_id = self._jira.get_jira_issue_field_id(rf.lower())
            try:
                jira_issue.get_field(jira_field_id)
            except AttributeError:
                self._logger.debug(
                    f"Rejecting Jira event because Jira field {rf} ({jira_field_id}) has not "
                    f"been enabled for Jira Project {jira_issue.fields.project} and Issue Type {jira_issue.fields.issuetype.name}."
                )
                return False

        # check that the Issue is flagged as synced
        if not self.__can_sync_to_fptr(jira_issue):
            self._logger.debug(
                f"Rejecting Jira event because Jira entity {jira_entity} has not been flagged as synced."
            )
            return False

        self._logger.debug("Jira event successfully accepted!")

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

        self._logger.debug(f"Processing Jira event...\n {event}")

        supported_jira_fields = []
        webhook_event = event["webhookEvent"]
        webhook_entity, webhook_action = self.__parse_jira_webhook_event(webhook_event)

        jira_key = event.get("issue", {}).get("key")
        if not jira_key:
            jira_entity = event.get(webhook_entity)
            jira_key = jira_entity.get("issueId")
        jira_issue = self._jira.issue(jira_key)

        if webhook_entity == "issue":
            sg_entity = self._sync_jira_issue_to_sg(jira_issue)
            supported_jira_fields = self._supported_jira_fields_for_jira_event(
                jira_issue.fields.issuetype.name
            ) + [self.__jira_sync_in_fptr_field_id]
        else:
            jira_key = event[webhook_entity]["id"]
            sg_entity_type = "Note" if webhook_entity == "comment" else "TimeLog"
            sg_entity = self._sync_jira_entity_to_sg(
                jira_issue, jira_key, sg_entity_type, webhook_action
            )

        if webhook_action == "deleted":
            # the entity has been deleted during the sync of it with FPTR
            return True

        if not sg_entity:
            self._logger.debug(
                f"Error happened while processing Jira event: couldn't get FPTR associated entity."
            )
            return False

        jira_fields = []
        if "changelog" in event:
            for change in event["changelog"]["items"]:
                # special use case for parenting association
                if change.get("field") == "IssueParentAssociation":
                    jira_fields.append("parent")
                # Depending on the Jira server version, we can get the Jira field id
                # in the change payload or just the field name.
                # If we don't have the field id, retrieve it from our internal mapping.
                jira_field_id = change.get(
                    "fieldId"
                ) or self._jira.get_jira_issue_field_id(change["field"])
                if jira_field_id not in supported_jira_fields:
                    self._logger.debug(
                        f"Error happened while processing Jira event: unsupported field {jira_field_id}"
                    )
                    continue
                jira_fields.append(jira_field_id)
        else:
            # we don't have a changelog, that means we're facing worklog/comment update so we want to sync everything
            jira_fields.append(self.__jira_sync_in_fptr_field_id)

        if self.__jira_sync_in_fptr_field_id in jira_fields:
            return self._sync_jira_fields_to_sg(jira_issue, jira_key, sg_entity)

        return self._sync_jira_fields_to_sg(
            jira_issue, jira_key, sg_entity, jira_fields
        )

    def __accept_shotgun_event_for_entities_not_flagged_as_synced(self, sg_entity, field, meta):
        """
        Helper method to check if an entity not flagged as synced (aka that doesn't have the field to initiate the
        sync) can be accepted when processing the sync from FPTR to Jira.
        """

        if field == self.__SG_RETIREMENT_FIELD:
            if not sg_entity.get(SHOTGUN_JIRA_ID_FIELD):
                self._logger.debug(
                    f"Rejecting Flow Production Tracking event: {sg_entity['type']} ({sg_entity['id']}) doesn't seem to "
                    f"be synced to Jira."
                )
                return False

        else:
            if not self.__get_linked_entity_synced_in_jira(sg_entity):
                previous_entities = []
                if meta.get("old_value"):
                    previous_entities.append(meta["old_value"])
                elif meta.get("removed"):
                    previous_entities.extend(meta["removed"])
                was_previously_linked = self.__was_previously_synced_in_jira(
                    previous_entities
                )
                if not was_previously_linked:
                    self._logger.debug(
                        f"Rejecting Flow Production Tracking event: {sg_entity['type']} ({sg_entity['id']}) "
                        f"is not linked to an entity already synced to Jira."
                    )
                    return False

        self._logger.debug("Flow Production Tracking event successfully accepted!")
        return True

    def __accept_shotgun_event_for_entities_synced_as_issues(self, sg_entity, jira_issue_type):
        """
        Helper method to check if an entity that will be synced as issue in Jira can be accepted when processing the
        sync from FPTR to Jira.
        """

        # check that the entity linked to the event has been flagged as ready-to-sync in FPTR
        # some special entities like Notes or TimeLogs don't need the flag as they are tied to other flagged entities
        if not sg_entity.get(SHOTGUN_SYNC_IN_JIRA_FIELD):
            self._logger.debug(
                f"Rejecting Flow Production Tracking event: {sg_entity['type']} ({sg_entity['id']}) "
                f"is not flagged as ready-to-sync."
            )
            return False

        # if we're trying to sync a FPTR as a Jira Issue, we need to make sure that the issue type exists in the
        # project and has the required field
        jira_project_key = sg_entity[f"project.Project.{SHOTGUN_JIRA_ID_FIELD}"]

        try:
            self._jira.issue_type_by_name(
                jira_issue_type, jira_project_key
            )
        except KeyError:
            self._logger.debug(
                f"Rejecting Flow Production Tracking event: issue type {jira_issue_type} "
                f"has not been enabled for project {jira_project_key} in Jira"
            )
            return False

        jira_project = self.get_jira_project(jira_project_key)
        if not jira_project:
            self._logger.debug(
                f"Rejecting Flow Production Tracking event because project {jira_project_key} doesn't exist in Jira"
            )
            return False

        required_fields = [JIRA_SHOTGUN_ID_FIELD, JIRA_SHOTGUN_TYPE_FIELD]
        jira_fields = self._jira.get_project_issue_type_fields(
            jira_project, jira_issue_type
        )
        for rf in required_fields:
            jira_field_id = self._jira.get_jira_issue_field_id(rf.lower())
            if jira_field_id not in jira_fields.keys():
                self._logger.debug(
                    f"Rejection Flow Production Tracking event because Jira field {rf} ({jira_field_id}) has not "
                    f"been enabled for Jira Project {jira_project} and Issue Type {jira_issue_type}"
                    "."
                )
                return False

        self._logger.debug("Flow Production Tracking event successfully accepted!")

        return True

    def _supported_shotgun_entities_for_shotgun_event(self):
        """
        Return the list of Flow Production Tracking entities that this handler can process for a
        Flow Production Tracking to Jira event.
        :returns: A list of strings.
        """
        return [m["sg_entity"] for m in self.__entity_mapping]

    def _supported_shotgun_fields_for_shotgun_event(self, entity_type):
        """
        Return the list of Flow Production Tracking fields that this handler can process for a
        Flow Production Tracking to Jira event.
        :param entity_type: The type of FPTR entity to process.
        :type entity_type: str
        :returns: A list of strings.
        """

        if entity_type == "Note":
            return self.__NOTE_SG_FIELDS

        sg_fields = []
        for entity_mapping in self.__entity_mapping:
            if entity_mapping["sg_entity"] == entity_type:
                sg_fields = [m["sg_field"] for m in entity_mapping["field_mapping"]]
            if entity_mapping.get("status_mapping"):
                sg_fields.append(entity_mapping["status_mapping"]["sg_field"])

        if entity_type == "TimeLog":
            sg_fields += self.__TIMELOG_EXTRA_SG_FIELDS

        return sg_fields

    @staticmethod
    def _supported_jira_webhook_events():
        """
        Return the list of Jira Webhook events that this handler can process for a Jira to Flow Production Tracking
        event.
        :returns: A list of strings.
        """
        return [
            "jira:issue_created",
            "jira:issue_updated",
            "comment_created",
            "comment_updated",
            "comment_deleted",
            "worklog_created",
            "worklog_updated",
            "worklog_deleted",
        ]

    def _supported_jira_issue_types_for_jira_event(self):
        """
        Return the list of Jira Issue Types that this handler can process for a Jira to Flow Production Tracking event.
        :returns: A list of strings.
        """
        jira_issue_types = []
        for em in self.__entity_mapping:
            if em.get("jira_issue_type"):
                jira_issue_types.append(em["jira_issue_type"])
        return jira_issue_types

    def _supported_jira_fields_for_jira_event(self, jira_entity_type):
        """
        Return the list of Jira fields that this handler can process for a Jira to Flow Production Tracking event.
        :param jira_entity_type: The type of Jira entity to process.
        :type jira_entity_type: str
        :returns: A list of strings.
        """

        jira_fields = []

        # Jira worklogs
        if jira_entity_type == "Worklog":
            entity_mapping = self.__get_sg_entity_settings("TimeLog")
            jira_fields = [m["jira_field"] for m in entity_mapping["field_mapping"]]

        # Jira issues
        else:
            for entity_mapping in self.__entity_mapping:
                if entity_mapping.get("jira_issue_type") == jira_entity_type:
                    jira_fields = [
                        m["jira_field"] for m in entity_mapping["field_mapping"]
                    ]
                if entity_mapping.get("status_mapping"):
                    jira_fields.append("status")

        return jira_fields

    def __sg_get_entity_fields(self, entity_type):
        """
        Get all the FPTR fields required when querying the database.
        :param entity_type: The type of FPTR entity we want to query the fields for.
        :type entity_type: str
        :returns: A list of strings.
        """
        return [
            SHOTGUN_SYNC_IN_JIRA_FIELD,
            SHOTGUN_JIRA_ID_FIELD,
            "project",
            f"project.Project.{SHOTGUN_JIRA_ID_FIELD}",
            "created_by",
        ] + self._supported_shotgun_fields_for_shotgun_event(entity_type)

    def __get_sg_entity_settings(self, entity_type):
        """
        Returns the sync settings for the given FPTR entity type.
        :param entity_type: The type of FPTR entity we want to query the settings for.
        :type entity_type: str
        :returns: A dictionary with the sync settings.
        """
        for entity_mapping in self.__entity_mapping:
            if entity_mapping["sg_entity"] == entity_type:
                return entity_mapping
        return None

    def __get_jira_issue_type_settings(self, issue_type):
        """
        Returns the sync settings for the given Jira issue type.
        :param issue_type: The type of Jira issue we want to query the settings for.
        :type issue_type: str
        :returns: A dictionary with the sync settings.
        """
        for entity_mapping in self.__entity_mapping:
            if entity_mapping.get("jira_issue_type") == issue_type:
                return entity_mapping
        return None

    def __get_field_mapping(self, entity_type, jira_field=None, sg_field=None):
        """
        Return the field mapping between FPTR and Jira.
        :param entity_type: The type of FPTR entity we want to have the equivalent field for.
        :type entity_type: str
        :param jira_field: If provided, this method will return the associated FPTR field.
        :type jira_field: str
        :param sg_field: If provided, this method will return the associated Jira field.
        :type sg_field: str
        :returns: The associated field as string.
        """
        if not jira_field and not sg_field:
            raise ValueError("jira_field or sg_field must be provided")

        if jira_field and sg_field:
            raise ValueError(
                "Only jira_field or sg_field must be provided, but not both of them"
            )

        entity_mapping = self.__get_sg_entity_settings(entity_type)

        # special use cases for the status fields
        if (
            jira_field
            and jira_field == "status"
            and entity_mapping.get("status_mapping")
        ):
            return {
                "sg_field": entity_mapping["status_mapping"]["sg_field"],
                "jira_field": "status",
                "sync_direction": entity_mapping["status_mapping"].get(
                    "sync_direction", "both_way"
                ),
            }

        if (
            sg_field
            and entity_mapping.get("status_mapping")
            and sg_field == entity_mapping["status_mapping"]["sg_field"]
        ):
            return {
                "sg_field": sg_field,
                "jira_field": "status",
                "sync_direction": entity_mapping["status_mapping"].get(
                    "sync_direction", "both_way"
                ),
            }

        for f in entity_mapping["field_mapping"]:
            if jira_field and f["jira_field"] == jira_field:
                return f
            elif sg_field and f["sg_field"] == sg_field:
                return f

    def __get_status_mapping(self, entity_type, jira_status=None, sg_status=None):
        """
        Return the status mapping between FPTR and Jira.
        :param entity_type: The type of FPTR entity we want to have the equivalent field for.
        :type entity_type: str
        :param jira_status: If provided, this method will return the associated FPTR status.
        :type jira_status: str
        :param sg_status: If provided, this method will return the associated Jira status.
        :type sg_status: str
        :returns: The associated status as string.
        """
        if not sg_status and not jira_status:
            raise ValueError("sg_status or jira_status must be provided")

        if sg_status and jira_status:
            raise ValueError(
                "Only sg_status or jira_status must be provided, but not both of them"
            )

        entity_mapping = self.__get_sg_entity_settings(entity_type)
        for s_status, j_status in entity_mapping["status_mapping"]["mapping"].items():
            if sg_status and sg_status == s_status:
                return j_status
            elif jira_status and j_status == jira_status:
                return s_status

    def _get_jira_entity(self, sg_entity):
        """
        Get the Jira entity associated to the given FPTR entity.
        :param sg_entity: A FPTR entity dictionary.
        :type sg_entity: dict
        :returns: The associated Jira entity as a Jira object.
        """

        # we need to manage special entities like Note/Comment and TimeLog/Worklog apart
        if sg_entity["type"] == "Note":
            jira_issue_key, jira_comment_id = self.__parse_jira_key_from_sg_entity(
                sg_entity
            )
            return self._get_jira_issue_comment(jira_issue_key, jira_comment_id)

        elif sg_entity["type"] == "TimeLog":
            jira_issue_key, jira_worklog_id = self.__parse_jira_key_from_sg_entity(
                sg_entity
            )
            return self._get_jira_issue_worklog(jira_issue_key, jira_worklog_id)

        # for all other entities, we consider them as Jira issues
        else:
            jira_key = sg_entity[SHOTGUN_JIRA_ID_FIELD]
            jira_issue = self.get_jira_issue(jira_key)
            if not jira_issue:
                self._logger.warning(
                    f"Unable to find Jira Issue {jira_key} associated to the FPTR {sg_entity['type']} ({sg_entity['id']})"
                )
                return
            # once the issue has been found, make sure it is linked to the right FPTR entity
            jira_sg_id = int(
                getattr(jira_issue.fields, self._jira.jira_shotgun_id_field)
            )
            jira_sg_type = getattr(
                jira_issue.fields, self._jira.jira_shotgun_type_field
            )
            if jira_sg_id != sg_entity["id"] or jira_sg_type != sg_entity["type"]:
                self._logger.warning(
                    f"Bad Jira Issue {jira_issue}. Expected it to be linked to Flow Production Tracking "
                    f"{sg_entity['type']} ({sg_entity['id']}) but instead it is linked to Flow Production Tracking "
                    f"{jira_sg_type} ({jira_sg_id})."
                )
                return
            return jira_issue

    def _create_jira_entity(self, sg_entity, jira_project):
        """
        Create a Jira entity from a given FPTR entity.
        :param sg_entity: A FPTR entity dictionary representing the Jira entity to create.
        :type sg_entity: dict
        :param jira_project: The Jira project to create the Jira entity from.
        :type jira_project: jira.resources.Project
        :returns: The created Jira entity as object
        """

        # we need to manage special entities like Note/Comment and TimeLog/Worklog apart
        if sg_entity["type"] == "Note":
            jira_entity, jira_entity_key = self._create_jira_comment(sg_entity)

        elif sg_entity["type"] == "TimeLog":
            jira_entity, jira_entity_key = self._create_jira_worklog(sg_entity)

        # Considering all the other FPTR entities as Jira issues
        else:
            jira_entity, jira_entity_key = self._create_jira_issue(sg_entity, jira_project)

        # update FPTR with the Jira data
        if jira_entity:
            sg_data = {
                SHOTGUN_JIRA_ID_FIELD: jira_entity_key,
            }
            if isinstance(jira_entity, jira.resources.Issue):
                sg_data[SHOTGUN_JIRA_URL_FIELD] = {
                    "url": jira_entity.permalink(),
                    "name": "View in Jira",
                }
            self._shotgun.update(sg_entity["type"], sg_entity["id"], sg_data)

        return jira_entity

    def _create_jira_comment(self, sg_entity):
        """Helper method to create a Jira comment from a FPTR Note entity."""

        # to avoid confusion, even if the Note is linked to many synced entities, we're going to associate
        # this Note to only one Issue in Jira
        if len(sg_entity["tasks"]) > 1:
            self._logger.warning(
                f"FPTR Note ({sg_entity['id']}) is linked to more than one Task. "
                f"Comment in Jira will only be created for one Issue."
            )
        sg_linked_entity = self.__get_linked_entity_synced_in_jira(sg_entity)
        jira_issue = self._get_jira_entity(sg_linked_entity)
        if not jira_issue:
            return None, None

        jira_entity = self._jira.add_comment(
            jira_issue,
            self._hook.compose_jira_comment_body(sg_entity),
            visibility=None,  # TODO: check if Note properties should drive this
            is_internal=False,
        )
        jira_entity_key = "%s/%s" % (jira_issue.key, jira_entity.id)

        return jira_entity, jira_entity_key

    def _create_jira_worklog(self, sg_entity):
        """Helper method to create a Jira worklog from a FPTR TimeLog entity."""

        started_date = None
        if sg_entity.get("date"):
            started_date = datetime.datetime.strptime(
                sg_entity["date"], self._hook.SG_DATE_FORMAT
            )

        # here, we're assuming that all the entities sync in Jira are issues
        sg_linked_entity = self.__get_linked_entity_synced_in_jira(sg_entity)
        jira_issue = self._get_jira_entity(sg_linked_entity)
        if not jira_issue:
            return None, None

        jira_entity = self._jira.add_worklog(
            jira_issue,
            timeSpentSeconds=sg_entity["duration"] * 60,
            started=started_date,
        )
        jira_entity_key = "%s/%s" % (jira_issue.key, jira_entity.id)

        return jira_entity, jira_entity_key

    def _create_jira_issue(self, sg_entity, jira_project):
        """Helper method to create a Jira issue from a FPTR entity."""

        # Retrieve the reporter, either the user who created the Entity or the
        # Jira user used to run the syncing.
        reporter = self._jira.myself()
        created_by = sg_entity["created_by"]
        if created_by["type"] == "HumanUser":
            user = self._shotgun.consolidate_entity(created_by)
            if user and user.get("email"):
                jira_user = self.get_jira_user(user["email"], jira_project)
                if jira_user:
                    reporter = jira_user
        else:
            self._logger.debug(
                f"Ignoring created_by '{created_by}' since it's not a HumanUser."
            )

        # If a FPTR field has been associated to the Jira summary field in the settings, use it
        # otherwise use the entity name
        summary_field = self.__get_field_mapping(
            sg_entity["type"], jira_field="summary"
        )
        if summary_field:
            summary_field = summary_field["sg_field"]
        else:
            summary_field = self._shotgun.get_entity_name_field(sg_entity["type"])

        shotgun_url = self._shotgun.get_entity_page_url(sg_entity)

        self._logger.debug(
            f"Creating Jira Issue in Project {jira_project} for Flow Production Tracking {sg_entity['type']} "
            f"{sg_entity['name']} ({sg_entity['id']})"
        )

        entity_settings = self.__get_sg_entity_settings(sg_entity["type"])
        sync_in_fptr = (
            "False"
            if entity_settings.get("sync_direction", "both_way") == "sg_to_jira"
            else "True"
        )
        data = {
            "project": jira_project.raw,
            "summary": sg_entity[summary_field].replace("\n", "").replace("\r", ""),
            "description": "",
            self._jira.jira_shotgun_id_field: str(sg_entity["id"]),
            self._jira.jira_shotgun_type_field: sg_entity["type"],
            self._jira.jira_shotgun_url_field: shotgun_url,
            self.__jira_sync_in_fptr_field_id: {"value": sync_in_fptr},
            "reporter": reporter,
        }
        jira_entity = self._jira.create_issue_from_data(
            jira_project,
            entity_settings["jira_issue_type"],
            data,
        )
        jira_entity_key = jira_entity.key

        return jira_entity, jira_entity_key

    def _delete_jira_entity(self, sg_entity, update_sg=False):
        """
        Delete the Jira entity associated to the given FPTR entity.
        :param sg_entity: The Flow Production Tracking entity we want to delete the Jira associated entity from.
        :type sg_entity: dict
        :param update_sg: If True, the Jira key associated to the FPTR entity will be cleaned up.
        """

        self._logger.debug(
            f"Deleting Jira entity associated to Flow Production Tracking {sg_entity['type']} ({sg_entity['id']})..."
        )

        jira_entity = self._get_jira_entity(sg_entity)
        if not jira_entity:
            self._logger.debug(
                f"Couldn't delete jira entity: couldn't find Jira entity associated to FPTR {sg_entity['type']} "
                f"({sg_entity['id']}) (Jira key {sg_entity[SHOTGUN_JIRA_ID_FIELD]})"
            )
            return False
        jira_entity.delete()

        if update_sg:
            self._shotgun.update(
                sg_entity["type"], sg_entity["id"], {SHOTGUN_JIRA_ID_FIELD: ""}
            )

        return True

    def _sync_sg_fields_to_jira(self, sg_entity, jira_entity, field_name=None):
        """
        Sync a list of FPTR fields to Jira.
        :param sg_entity: The Flow Production Tracking entity we want to sync the fields from.
        :type sg_entity: dict
        :param jira_entity: The Jira entity we want to sync the fields to.
        :type jira_entity: jira.resources.Issue or jira.resources.Worklog or jira.resources.Comment
        :param field_name: Optional field name to sync. If not one is supplied, all the fields associated to the FPTR
            entity will be synced.
        :returns: True if everything went well, False if errors happened
        """

        jira_fields = {}
        sync_with_errors = False

        # Notes have a special behavior
        if sg_entity["type"] == "Note":
            if field_name == "tasks":
                return True
            comment_body = self._hook.compose_jira_comment_body(sg_entity)
            jira_entity.update(body=comment_body)
            return True

        # if no field name is supplied, that means we want to sync all the fields so get them
        if not field_name:
            sg_fields = self._supported_shotgun_fields_for_shotgun_event(
                sg_entity["type"]
            )
        else:
            sg_fields = [field_name]

        # query Jira to get all the editable fields for the current issue type
        editable_jira_fields = (
            self._jira.get_jira_issue_edit_meta(jira_entity)
            if isinstance(jira_entity, jira.resources.Issue)
            else {}
        )

        for sg_field in sg_fields:

            # TimeLog specific uses cases
            if sg_entity["type"] == "TimeLog":

                if sg_field in ["user", "description"]:
                    worklog_comment = self._hook.compose_jira_worklog_comment(sg_entity)
                    jira_fields["comment"] = worklog_comment
                    continue

                # don't do anything, the special use case has been handled when processing the FPTR event
                # and in case we're syncing all the fields, we don't need to sync this one because it has already been
                # handled at creation time
                if sg_field == "entity":
                    continue

            field_mapping = self.__get_field_mapping(
                sg_entity["type"], sg_field=sg_field
            )

            if field_mapping.get("sync_direction") == "jira_to_sg":
                continue

            # get the associated Jira field
            jira_field = field_mapping["jira_field"]

            if jira_field == "watches":
                self._sync_sg_watchers_to_jira(sg_entity[sg_field], jira_entity)
                continue

            if jira_field == "status":
                self._sync_sg_status_to_jira(
                    sg_entity[sg_field], sg_entity["type"], jira_entity
                )
                continue

            if jira_field in ["parent", self.__JIRA_CHILDREN_FIELD]:
                self._sync_hierarchy_to_jira(
                    sg_entity[sg_field], jira_entity, jira_field
                )
                continue

            # check that we have permission to edit this field
            if (
                sg_entity["type"] not in self.__ENTITIES_NOT_FLAGGED_AS_SYNCED
                and jira_field not in editable_jira_fields
            ):
                self._logger.warning(
                    f"Not syncing Flow Production Tracking {sg_entity['type']}.{sg_field} to Jira. "
                    f"Target Jira {jira_entity.fields.issuetype}.{jira_field} field is not editable"
                )
                sync_with_errors = True
                continue

            # get the Jira value associated to the SG value as sometimes we need to perform some kind of conversion
            try:
                if isinstance(sg_entity[sg_field], list):
                    jira_value = self._hook.get_jira_value_from_sg_list(
                        sg_entity[sg_field],
                        jira_entity,
                        jira_field,
                        editable_jira_fields.get(jira_field),
                    )
                else:
                    jira_value = self._hook.get_jira_value_from_sg_value(
                        sg_entity[sg_field],
                        jira_entity,
                        jira_field,
                        editable_jira_fields.get(jira_field),
                    )
            except Exception as e:
                self._logger.warning(
                    f"Not syncing Flow Production Tracking {sg_entity['type']}.{sg_field} to Jira. "
                    f"Error occurred when trying to convert FPTR value to Jira value: {e}"
                )
                sync_with_errors = True
                continue

            # Couldn't get a Jira value, cancel update
            if jira_value is None and sg_entity[sg_field]:
                self._logger.warning(
                    f"Not syncing Flow Production Tracking {sg_entity['type']}. "
                    f"Couldn't translate Flow Production Tracking value {sg_entity[sg_field]} to a valid value "
                    f"for Jira field {jira_field}"
                )
                sync_with_errors = True
                continue

            jira_fields[jira_field] = jira_value

        if jira_fields:
            self._logger.debug(f"Updating Jira fields: {jira_fields}")
            jira_entity.update(fields=jira_fields)

        # if a full sync is required for a Jira Issue, we also need to sync its associated comments and worklogs
        if (
            sg_entity["type"] not in self.__ENTITIES_NOT_FLAGGED_AS_SYNCED
            and not field_name
        ):
            worklog_sync_with_error = self._sync_sg_linked_entities_to_jira(
                sg_entity, "TimeLog", jira_entity
            )
            comment_sync_with_error = self._sync_sg_linked_entities_to_jira(
                sg_entity, "Note", jira_entity
            )
            if worklog_sync_with_error or comment_sync_with_error:
                sync_with_errors = True

        return not sync_with_errors

    def _sync_sg_watchers_to_jira(self, sg_value, jira_issue):
        """
        Update the Jira Issue watchers list.

        :param sg_value: FPTR entities representing the Jira watchers
        :type sg_value: dict or list of dict
        :param jira_issue: Jira issue we want to update the watchers
        :type jira_issue: jira.resources.Issue
        :returns: True if everything went well, False if errors happened
        """

        current_watchers = []

        # specific case where the FPTR can be a custom single entity field
        if isinstance(sg_value, dict):
            sg_value = [sg_value]

        for user in sg_value:

            # only supporting Person entity (can also be a Group for example)
            if user["type"] != "HumanUser":
                continue

            # start by adding the all the FPTR users to the watchlist
            sg_user = self._shotgun.consolidate_entity(user)
            if sg_user:

                jira_user = self._jira.find_jira_user(
                    sg_user["email"], jira_issue=jira_issue
                )
                if jira_user:
                    current_watchers.append(jira_user.accountId)
                    self._logger.debug(
                        f"Adding {jira_user.displayName} to {jira_issue} watchers list."
                    )
                    # add_watcher method supports both user_id and accountId properties
                    self._jira.add_watcher(jira_issue, jira_user.accountId)

        # now, go through all watchers and remove the one that are not in FPTR anymore
        for jira_watcher in self._jira.watchers(jira_issue).watchers:
            if jira_watcher.accountId not in current_watchers:
                self._logger.debug(
                    f"Removing {jira_watcher.displayName} from {jira_issue} watchers list."
                )
                # In older versions of the client (<= 3.0) we used jira_user.user_id
                # However, newer versions of the remove_watcher method supports name search
                self._jira.remove_watcher(jira_issue, jira_watcher.displayName)

        return True

    def _sync_sg_status_to_jira(self, sg_value, entity_type, jira_issue):
        """
        Update the Jira Issue status.

        :param sg_value: FPTR entity status
        :type sg_value: str
        :param entity_type: The type of the FPTR entity we want to update the status from
        :type entity_type: str
        :param jira_issue: Jira issue we want to update the status
        :type jira_issue: jira.resources.Issue
        :returns: True if everything went well, False if errors happened
        """

        jira_status = self.__get_status_mapping(entity_type, sg_status=sg_value)
        if not jira_status:
            self._logger.warning(
                "Unable to find a matching Jira status for Flow Production Tracking "
                f"status '{sg_value}'"
            )
            return False

        return self._jira.set_jira_issue_status(
            jira_issue,
            jira_status,
            f"Updated from Flow Production Tracking {entity_type} moving to {sg_value}",
        )

    def _sync_sg_linked_entities_to_jira(
        self, sg_entity, linked_entity_type, jira_issue
    ):
        """
        Perform a full sync for each FPTR related entities linked to a FPTR entity representing a Jira Issue.
        A related entity can be a FPTR TimeLog or Note.
        :param sg_entity: FPTR entity we want to sync the related entities from
        :type sg_entity: dict
        :param linked_entity_type: Type of the FPTR related entities we're trying to sync
        :type linked_entity_type: str
        :param jira_issue: Jira issue associated to the FPTR entity the original sync if performed from
        :type jira_issue: jira.resources.Issue
        :returns: True if everything went well, False if errors happened
        """

        if (
            linked_entity_type
            not in self._supported_shotgun_entities_for_shotgun_event()
        ):
            return False

        linked_entity_field = "tasks" if linked_entity_type == "Note" else "entity"

        sg_linked_entities = self._shotgun.find(
            linked_entity_type,
            [[linked_entity_field, "is", sg_entity]],
            self.__sg_get_entity_fields(linked_entity_type),
        )

        sync_with_error = False
        for e in sg_linked_entities:
            if not e[SHOTGUN_JIRA_ID_FIELD]:
                jira_entity = self._create_jira_entity(e, jira_issue.fields.project)
            else:
                jira_issue_key, jira_entity_key = self.__parse_jira_key_from_sg_entity(
                    e
                )
                if jira_issue_key != jira_issue.key:
                    self._logger.debug(
                        f"FPTR Entity {e['type']} ({e['id']}) already synced with another Jira Issue "
                        f"({e[SHOTGUN_JIRA_ID_FIELD]}). Skipping update."
                    )
                    continue
                jira_entity = self._get_jira_entity(e)
            if not jira_entity:
                self._logger.warning(
                    f"Couldn't get Jira entity for FPTR {e['type']} ({e['id']})"
                )
                sync_with_error = True
                continue
            self._sync_sg_fields_to_jira(e, jira_entity)

        # TODO: do we want to sync with reciprocity in JIRA?

        return sync_with_error

    def _sync_hierarchy_to_jira(self, sg_linked_entities, jira_issue, jira_field):
        """
        Sync the FPTR parent/child relationship to Jira.
        :param sg_linked_entities: The FPTR entity/ies used as parent or child of the associated issue. It can be None
            if the field in FPTR is empty. It will be a list if we are trying to sync children but it will be a single
            entity if we're trying to sync the parent
        :type sg_linked_entities: dict or list
        :param jira_issue: Jira issue we want to update the parent
        :type jira_issue: jira.resources.Issue
        :param jira_field: Jira field we want to update, it will drive the hierarchy direction
            (parent to child or child to parent)
        :type jira_field: str
        :returns: True if everything went well, False if errors happened
        """

        sync_with_error = False
        jira_keys = []

        if not isinstance(sg_linked_entities, list):
            sg_linked_entities = [sg_linked_entities]

        # first, loop through all the FPTR linked entity to make sure new entities are correctly linked
        for sg_entity in sg_linked_entities:

            jira_parent = None
            jira_child = (
                None if jira_field == self.__JIRA_CHILDREN_FIELD else jira_issue
            )

            if sg_entity:

                # make sure the entity linked to the current FPTR entity is also synced to Jira and already exist
                entity_mapping = self.__get_sg_entity_settings(sg_entity["type"])
                if not entity_mapping:
                    self._logger.debug(
                        f"Couldn't find entity mapping for {sg_entity['type']} in the settings. Skipping hierarchy syncing."
                    )
                    sync_with_error = True
                    continue

                sg_consolidated_entity = self._shotgun.consolidate_entity(
                    sg_entity, [SHOTGUN_JIRA_ID_FIELD]
                )

                if sg_consolidated_entity.get(SHOTGUN_JIRA_ID_FIELD) is None:
                    self._logger.debug(
                        f"Couldn't find Jira Key for linked entity {sg_consolidated_entity['type']} ({sg_consolidated_entity['id']}). Skipping hierarchy syncing."
                    )
                    sync_with_error = True
                    continue

                jira_keys.append(sg_consolidated_entity[SHOTGUN_JIRA_ID_FIELD])

                jira_linked_issue = self._jira.issue(
                    sg_consolidated_entity[SHOTGUN_JIRA_ID_FIELD]
                )
                if not jira_linked_issue:
                    self._logger.warning(
                        f"Couldn't find Jira Issue associated to Jira Key ({sg_consolidated_entity[SHOTGUN_JIRA_ID_FIELD]}). Skipping hierarchy syncing."
                    )
                    sync_with_error = True
                    continue

                if jira_field == "parent":
                    jira_parent = {"key": jira_linked_issue.key}
                else:
                    jira_parent = {"key": jira_issue.key}
                    jira_child = jira_linked_issue

            if jira_child:
                jira_child.update(fields={"parent": jira_parent})

        # now, we need to go through each issue linked to the parent issue to check if they are still linked in FPTR
        # if not, we need to remove their links in Jira
        if jira_field == self.__JIRA_CHILDREN_FIELD:

            jira_children = self.__get_issue_children(jira_issue)
            for c in jira_children:
                if c.key not in jira_keys:
                    c.update(fields={"parent": None})

        return not sync_with_error

    def _sync_jira_issue_to_sg(self, jira_issue):
        """
        Get the FPTR entity linked to the JIra Issue. If the entity doesn't exist yet in FPTR, it will be created.
        :param jira_issue: Jira issue we want to get the associated FPTR entity from
        :type jira_issue: jira.resources.Issue
        :returns: The associated FPTR entity
        :rtype: dict
        """

        entity_mapping = self.__get_jira_issue_type_settings(
            jira_issue.fields.issuetype.name
        )
        sg_entity_type = entity_mapping.get("sg_entity")

        sg_entity = self._shotgun.find_one(
            sg_entity_type,
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            self.__sg_get_entity_fields(sg_entity_type),
        )

        if not sg_entity:

            # if some FPTR data was previously associated to the Jira issue but we cannot found the FPTR entity
            # that means something has happened
            sg_type = getattr(jira_issue.fields, self._jira.jira_shotgun_type_field)
            sg_id = getattr(jira_issue.fields, self._jira.jira_shotgun_id_field)
            if sg_type or sg_id:
                self._logger.warning(
                    f"Error happened while processing Jira event: Jira Issue {jira_issue.key} is already synced "
                    f"to a FPTR {sg_type} ({sg_id}) entity that couldn't be found in FPTR."
                )
                return False

            # otherwise, we want to create the FPTR entity
            sg_entity_name_field = self._shotgun.get_entity_name_field(sg_entity_type)
            jira_name_field = self.__get_field_mapping(
                sg_entity_type, sg_field=sg_entity_name_field
            )
            if jira_name_field:
                jira_name_field = jira_name_field["jira_field"]
            else:
                jira_name_field = "summary"

            sg_project = self._shotgun.find_one(
                "Project",
                [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.fields.project.key]],
            )

            sync_in_jira = (
                False
                if entity_mapping.get("sync_direction", "both_way") == "jira_to_sg"
                else True
            )

            sg_data = {
                "project": sg_project,
                sg_entity_name_field: getattr(jira_issue.fields, jira_name_field),
                SHOTGUN_JIRA_ID_FIELD: jira_issue.key,
                SHOTGUN_JIRA_URL_FIELD: {
                    "url": jira_issue.permalink(),
                    "name": "View in Jira",
                },
                SHOTGUN_SYNC_IN_JIRA_FIELD: sync_in_jira,
            }

            sg_entity = self._shotgun.create(sg_entity_type, sg_data)

            # update Jira with the FPTR entity data
            jira_fields = {
                self._jira.jira_shotgun_type_field: sg_entity["type"],
                self._jira.jira_shotgun_id_field: str(sg_entity["id"]),
                self._jira.jira_shotgun_url_field: self._shotgun.get_entity_page_url(
                    sg_entity
                ),
            }
            jira_issue.update(fields=jira_fields)

        return sg_entity

    def _sync_jira_entity_to_sg(
        self, jira_issue, jira_entity_id, sg_entity_type, webhook_action
    ):
        """
        Get the FPTR entity linked to a Jira entity (that is not an Issue).
        If the entity doesn't exist yet in FPTR, it will be created.
        It the entity doesn't exist in Jira anymore, it will be deleted in FPTR.
        :param jira_issue: Jira issue linked to the Jira entity we want to get the FPTR entity from
        :type jira_issue: jira.resources.Issue
        :param jira_entity_id: Id of the Jira entity we want to get the FPTR entity from
        :type jira_entity_id: str
        :param sg_entity_type: Type of the FPTR entity we want to act on
        :type sg_entity_type: str
        :param webhook_action: Type of the action we want to perform (creation/update/deletion)
        :type webhook_action: str
        :returns: The associated FPTR entity if it still exists, None otherwise
        :rtype: dict or None
        """

        # first, check that the Jira entity we're trying to sync is associated to a Jira Issue already synced in FPTR

        entity_mapping = self.__get_jira_issue_type_settings(
            jira_issue.fields.issuetype.name
        )
        sg_linked_entity_type = entity_mapping.get("sg_entity")

        # get the PTR entity associated to the Jira Issue
        sg_linked_entities = self._shotgun.find(
            sg_linked_entity_type,
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
            fields=self.__sg_get_entity_fields(sg_linked_entity_type),
        )

        if len(sg_linked_entities) > 1:
            self._logger.debug(
                f"Error happened while processing Jira event: more than one {sg_linked_entity_type} "
                f"exists in Flow Production Tracking with Jira key {jira_issue.key}."
            )
            return False

        elif len(sg_linked_entities) == 0:
            self._logger.debug(
                f"Error happened while processing Jira event: couldn't find any {sg_linked_entity_type} "
                f"in Flow Production Tracking with Jira key {jira_issue.key}"
            )
            return False

        if not sg_linked_entities[0][SHOTGUN_SYNC_IN_JIRA_FIELD]:
            self._logger.debug(
                f"Error happened while processing Jira event: The associated Flow "
                f"Production Tracking {sg_entity_type} is not flagged to be synced."
            )
            return False

        # now, check for the entity itself

        sg_jira_key = "%s/%s" % (jira_issue.key, jira_entity_id)

        sg_entities = self._shotgun.find(
            sg_entity_type,
            [[SHOTGUN_JIRA_ID_FIELD, "is", sg_jira_key]],
            self.__sg_get_entity_fields(sg_entity_type),
        )

        if len(sg_entities) > 1:
            self._logger.debug(
                f"Error happened while processing Jira event: more than one {sg_entity_type} "
                f"exists in Flow Production Tracking with Jira key {sg_jira_key}."
            )
            return False

        if len(sg_entities) == 0:
            if webhook_action == "deleted":
                self._logger.debug(
                    f"Error happened while processing Jira event: couldn't find any {sg_entity_type} "
                    f"in Flow Production Tracking with Jira key {sg_jira_key}"
                )
                return False

            sg_project = self._shotgun.find_one(
                "Project",
                [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.fields.project.key]],
            )

            sg_data = {
                "project": sg_project,
                SHOTGUN_JIRA_ID_FIELD: sg_jira_key,
            }

            if sg_entity_type == "TimeLog":
                sg_data["entity"] = sg_linked_entities[0]
            else:
                sg_data["tasks"] = [sg_linked_entities[0]]

            return self._shotgun.create(sg_entity_type, sg_data)

        # we want to delete the entity in FPTR
        if webhook_action == "deleted":
            self._shotgun.delete(sg_entity_type, sg_entities[0]["id"])

        return sg_entities[0]

    def _sync_jira_fields_to_sg(
        self, jira_issue, jira_key, sg_entity, jira_fields=None
    ):
        """
        Sync a list of Jira fields to FPTR.
        :param jira_issue: Jira issue we want to sync the fields from or linked to the Jira entity we want to sync the
            fields from
        :type jira_issue: jira.resources.Issue
        :param jira_key: Key of the Jira entity we want to sync the fields from. The Jira entity could be an Issue,
            a Worklog or a Comment
        :type jira_key: str
        :param sg_entity: The Flow Production Tracking entity we want to sync the fields to
        :type sg_entity: dict
        :param jira_fields: Optional list of fields name to sync. If not one is supplied, all the fields associated to
            the Jira entity will be synced.
        :type: list
        :returns: True if everything went well, False if errors happened
        """

        sync_with_errors = False
        jira_entity = jira_issue
        full_sync = True if not jira_fields else False

        if sg_entity["type"] == "Note":
            return self._sync_jira_comment_to_sg(jira_issue.key, jira_key, sg_entity)
        elif sg_entity["type"] == "TimeLog":
            issue_type = "Worklog"
            jira_entity = self._get_jira_issue_worklog(jira_issue, jira_key)
            jira_entity_key = jira_entity.id
        else:
            issue_type = jira_issue.fields.issuetype.name
            jira_entity_key = jira_issue.key

        if jira_fields is None:
            jira_fields = self._supported_jira_fields_for_jira_event(issue_type)

        sg_data = {}

        for jira_field in jira_fields:

            field_mapping = self.__get_field_mapping(
                sg_entity["type"], jira_field=jira_field
            )

            if field_mapping.get("sync_direction") == "sg_to_jira":
                continue

            # get the associated FPTR field
            sg_field = field_mapping["sg_field"]

            # make sure the FPTR field is editable
            sg_field_schema = self._shotgun.get_field_schema(
                sg_entity["type"], sg_field
            )
            if not sg_field_schema["editable"]["value"]:
                self._logger.warning(
                    f"Not syncing Jira {issue_type}.{jira_field} to Flow Production Tracking . "
                    f"Target Flow Production Tracking {sg_entity['type']}.{sg_field} field is not editable"
                )
                sync_with_errors = True
                continue

            try:
                if isinstance(jira_entity, jira.resources.Issue):
                    jira_value = getattr(jira_entity.fields, jira_field)
                else:
                    jira_value = getattr(jira_entity, jira_field)
            except AttributeError:
                if jira_field != "parent":
                    self._logger.debug(
                        f"Couldn't find jira field '{jira_field}' value for current {issue_type} ({jira_entity_key})"
                    )
                    sync_with_errors = True
                    continue
                jira_value = None

            if jira_field == "watches":
                sg_value = []
                for w in self._jira.watchers(jira_issue).watchers:
                    sg_user = self._hook.get_sg_user_from_jira_user(w)
                    sg_value.append(sg_user)

            elif jira_field == "status":
                sg_value = (
                    self.__get_status_mapping(
                        sg_entity["type"], jira_status=str(jira_value)
                    )
                    if jira_value
                    else None
                )
                if not sg_value:
                    self._logger.debug(
                        f"Couldn't find FPTR status associated to Jira Issue Status {jira_value}. "
                        f"Skipping status update"
                    )
                    continue

            elif jira_field == "parent":
                sg_value = self.__get_sg_entity_from_jira_issue(jira_value)

            elif jira_field == "comment" and isinstance(
                jira_entity, jira.resources.Worklog
            ):
                sg_value, sg_user = self._hook.extract_jira_worklog_data(jira_value)
                if sg_user:
                    sg_value = sg_value.strip()
                    sg_data["user"] = sg_user

            else:
                try:
                    sg_value = self._hook.get_sg_value_from_jira_value(
                        jira_value, jira_entity, sg_entity["project"], sg_field_schema
                    )
                except Exception as e:
                    self._logger.warning(
                        f"Not syncing Jira {issue_type}.{jira_field} to Flow Production Tracking . "
                        f"Error occurred when trying to convert FPTR value to Jira value: {e}"
                    )
                    sync_with_errors = True
                    continue

            sg_data[sg_field] = sg_value

        # if a full sync is required and the entity is mapped to an issue, we need to sync the worklogs and the comments
        # as well
        if full_sync and sg_entity["type"] not in self.__ENTITIES_NOT_FLAGGED_AS_SYNCED:
            comment_sync_without_error = self._sync_jira_comments_to_sg(jira_entity)
            worklog_sync_without_error = self._sync_jira_worklogs_to_sg(jira_entity)
            if not comment_sync_without_error or not worklog_sync_without_error:
                sync_with_errors = True

        if sg_data:
            self._shotgun.update(sg_entity["type"], sg_entity["id"], sg_data)

        return not sync_with_errors

    def _sync_jira_worklogs_to_sg(self, jira_issue):
        """
        Sync the Jira Issue worklogs to FPTR.

        :param jira_issue: Jira Issue we want to sync the worklogs from
        :type jira_issue: jira.resources.Issue
        :returns: True if everything works well, False otherwise
        """

        if "TimeLog" not in self._supported_shotgun_entities_for_shotgun_event():
            return True

        existing_jira_worklogs = []
        sync_with_errors = False

        # first, push all the comments to FPTR
        for jira_worklog in self._jira.worklogs(jira_issue.key):
            existing_jira_worklogs.append("%s/%s" % (jira_issue.key, jira_worklog.id))
            sg_entity = self._sync_jira_entity_to_sg(
                jira_issue, jira_worklog.id, "TimeLog", None
            )
            if not sg_entity:
                sync_with_errors = True
            if not self._sync_jira_fields_to_sg(
                jira_issue, jira_worklog.id, sg_entity, None
            ):
                sync_with_errors = True

        # then, if the sync deletion flag is enabled, remove the timelogs that doesn't exist anymore in Jira
        sync_settings = self.__get_sg_entity_settings("TimeLog")
        if sync_settings.get("sync_deletion_direction") in [None, "sg_to_jira"]:
            return not sync_with_errors

        sg_timelogs = self._shotgun.find(
            "TimeLog",
            [[f"entity.Task.{SHOTGUN_JIRA_ID_FIELD}", "is", jira_issue.key]],
            [SHOTGUN_JIRA_ID_FIELD],
        )
        for sg_timelog in sg_timelogs:
            if (
                sg_timelog.get(SHOTGUN_JIRA_ID_FIELD)
                and sg_timelog[SHOTGUN_JIRA_ID_FIELD] not in existing_jira_worklogs
            ):
                self._shotgun.delete("TimeLog", sg_timelog["id"])

        return not sync_with_errors

    def _sync_jira_comments_to_sg(self, jira_issue):
        """
        Sync the Jira Issue comments to FPTR.

        :param jira_issue: Jira Issue we want to sync the comments from
        :type jira_issue: jira.resources.Issue
        :returns: True if everything works well, False otherwise
        """

        if "Note" not in self._supported_shotgun_entities_for_shotgun_event():
            return True

        existing_jira_comments = []
        sync_with_errors = False

        # first, push all the comments to FPTR
        for jira_comment in self._jira.comments(jira_issue.key):
            existing_jira_comments.append("%s/%s" % (jira_issue.key, jira_comment.id))
            sg_entity = self._sync_jira_entity_to_sg(
                jira_issue, jira_comment.id, "Note", None
            )
            if not sg_entity:
                sync_with_errors = True

        # then, if the sync deletion flag is enabled, remove the notes that doesn't exist anymore in Jira

        sync_settings = self.__get_sg_entity_settings("Note")
        if sync_settings.get("sync_deletion_direction") in [None, "sg_to_jira"]:
            return not sync_with_errors

        sg_notes = self._shotgun.find(
            "Note",
            [[f"tasks.Task.{SHOTGUN_JIRA_ID_FIELD}", "is", jira_issue.key]],
            [SHOTGUN_JIRA_ID_FIELD],
        )
        for sg_note in sg_notes:
            if (
                sg_note.get(SHOTGUN_JIRA_ID_FIELD)
                and sg_note[SHOTGUN_JIRA_ID_FIELD] not in existing_jira_comments
            ):
                self._shotgun.delete("Note", sg_note["id"])

        return not sync_with_errors

    def _sync_jira_comment_to_sg(self, jira_issue_key, jira_comment_id, sg_entity):
        """
        Sync the content of a Jira comment to FPTR.

        :param jira_issue_key: Key of the Jira Issue associated to the comment we want to push the update from
        :type jira_issue_key: str
        :param jira_comment_id: Id of the Jira comment we want to push the update from
        :type jira_comment_id: str
        :param sg_entity: FPTR entity associated to the Jira comment we want to push the update from
        :type sg_entity: dict
        :returns: True if everything works well, False otherwise
        """

        jira_comment = self._get_jira_issue_comment(jira_issue_key, jira_comment_id)
        if not jira_comment:
            self._logger.debug(
                f"Couldn't find Jira comment ({jira_comment_id}) linked to Jira Issue ({jira_issue_key})"
            )
            return False

        sg_subject, sg_body, sg_author = self._hook.extract_jira_comment_data(
            jira_comment.body
        )

        if not sg_author:
            sg_author = self._hook.get_sg_user_from_jira_user(jira_comment.author)

        sg_data = {
            "subject": "Comment created from Jira" if not sg_subject else sg_subject,
            "content": sg_body,
            "user": sg_author,
        }

        self._shotgun.update(sg_entity["type"], sg_entity["id"], sg_data)

        return True

    def _get_jira_issue_comment(self, jira_issue_key, jira_comment_id):
        """
        Retrieve the Jira comment with the given id attached to the given Issue.

        .. note:: Jira comments can't live without being attached to an Issue,
                  so we use a "<Issue key>/<Comment id>" key to reference a
                  particular comment.

        :param str jira_issue_key: A Jira Issue key.
        :param str jira_comment_id: A Jira Comment id.
        :returns: A :class:`jira.Comment` instance or None.
        """
        jira_comment = None
        try:
            jira_comment = self._jira.comment(jira_issue_key, jira_comment_id)
        except jira.JIRAError as e:
            # Jira raises a 404 error if it can't find the Comment: catch the
            # error and keep the None value
            if e.status_code == 404:
                pass
            else:
                raise
        return jira_comment

    def _get_jira_issue_worklog(self, jira_issue_key, jira_worklog_id):
        """
        Retrieve the Jira worklog with the given id attached to the given Issue.

        .. note:: Jira worklogs can't live without being attached to an Issue,
                  so we use a "<Issue key>/<Worklog id>" key to reference a
                  particular worklog.

        :param str jira_issue_key: A Jira Issue key.
        :param str jira_worklog_id: A Jira Worklog id.
        :returns: A :class:`jira.Worklog` instance or None.
        """
        jira_worklog = None
        try:
            jira_worklog = self._jira.worklog(jira_issue_key, jira_worklog_id)
        except jira.JIRAError as e:
            # Jira raises a 404 error if it can't find the Worklog: catch the
            # error and keep the None value
            if e.status_code == 404:
                pass
            else:
                raise
        return jira_worklog

    def __get_sg_entity_from_jira_issue(self, jira_issue):
        """
        Get the FPTR entity associated to the given Jira Issue.

        :param jira_issue: The Jira Issue we want to get the associated FPTR entity from
        :type jira_issue: jira.resources.Issue
        :returns: The associated FPTR entity if we can find it, None otherwise.
        :rtype: dict or None
        """
        if not jira_issue:
            return None
        entity_mapping = self.__get_jira_issue_type_settings(
            jira_issue.fields.issuetype.name
        )
        return self._shotgun.find_one(
            entity_mapping["sg_entity"],
            [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.key]],
        )

    def __parse_jira_key_from_sg_entity(self, sg_entity):
        """
        Given a FPTR entity, parse the Jira ID field to get the Jira Issue key and the associated Jira entity ID if one
        is associated to the FPTR entity.
        :param sg_entity: The FPTR entity to parse the field.
        :type sg_entity: dict
        :returns: The Jira Issue key and the Jira entity ID if one is also associated (the ID will be None otherwise).
        """

        jira_key = sg_entity[SHOTGUN_JIRA_ID_FIELD]

        if sg_entity["type"] not in self.__ENTITIES_NOT_FLAGGED_AS_SYNCED:
            return jira_key, None

        parts = jira_key.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(
                f"Invalid Jira key {jira_key}, it must be in the format "
                "'<jira issue key>/<jira entity id>'"
            )
        return parts[0], parts[1]

    def __get_linked_entity_synced_in_jira(self, sg_entity):
        """
        Given a FPTR entity, get the linked entity that is also synced to Jira.
        :param sg_entity: The FPTR entity to get the linked entity from. It can be a TimeLog or a Note.
        :type sg_entity: dict
        :returns: The linked entity that is also synced to Jira if it can be found, None otherwise.
        :rtype: dict or None
        """

        sg_linked_entities = (
            sg_entity["tasks"] if sg_entity["type"] == "Note" else [sg_entity["entity"]]
        )
        for e in sg_linked_entities:
            if not e:
                continue
            sg_linked_entity = self._shotgun.find_one(
                e["type"],
                [["id", "is", e["id"]]],
                [SHOTGUN_JIRA_ID_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD],
            )
            if (
                sg_linked_entity[SHOTGUN_JIRA_ID_FIELD]
                and sg_linked_entity[SHOTGUN_SYNC_IN_JIRA_FIELD]
            ):
                # for now, even if the FPTR entity is linked to many entities, we're returning the first one
                # we can find with a Jira key
                return sg_linked_entity
        return None

    def __was_previously_synced_in_jira(self, sg_entities):
        """
        Given a list of FPTR entities, check if at least one of them has already been synced in Jira.
        :param sg_entities: The FPTR entities to check if they have already been synced.
        :type sg_entities: list of dict
        :returns: True if at least one of the entities has already been synced, False otherwise.
        """

        if not sg_entities:
            return False

        entities_id = [e["id"] for e in sg_entities]

        sg_entities = self._shotgun.find(
            sg_entities[0]["type"],
            [["id", "in", entities_id]],
            [SHOTGUN_SYNC_IN_JIRA_FIELD],
        )

        for e in sg_entities:
            if e.get(SHOTGUN_SYNC_IN_JIRA_FIELD):
                return True

        return False

    def __can_sync_to_fptr(self, jira_issue):
        """
        Check that, for a given Jira Issue, it can be synced to FPTR.
        :param jira_issue: The Jira Issue to check.
        :type jira_issue: jira.resources.Issue
        :returns: True if the Jira Issue can be synced to FPTR, False otherwise.
        """

        jira_field = jira_issue.get_field(self.__jira_sync_in_fptr_field_id)
        if not jira_field:
            return False
        return True if jira_field.value == "True" else False

    @staticmethod
    def __parse_jira_webhook_event(webhook_event):
        """
        Helper method to parse the Jira webhook event.
        :param webhook_event: The Jira webhook event to parse.
        :type webhook_event: str
        :returns: The Jira entity the action is done from as well as the action to perform
        """

        result = re.search(r"([\w]+)_([\w]+)", webhook_event)
        if not result:
            return None, None
        return result.group(1), result.group(2)

    def __get_issue_children(self, jira_issue):
        """
        Helper method to get all the children issues of a given Jira issue.
        :param jira_issue: The Jira Issue we want to get the children for.
        :type jira_issue: jira.resources.Issue
        :returns: The list of Jira Issue children.
        :rtype: list of jira.resources.Issue
        """
        return self._jira.search_issues(f"parent IN ('{jira_issue.key}')")
