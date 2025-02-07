# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import jira

from sg_jira.errors import InvalidJiraValue
from sg_jira.handlers import SyncHandler
from sg_jira.constants import (SHOTGUN_SYNC_IN_JIRA_FIELD, SHOTGUN_JIRA_ID_FIELD, SHOTGUN_JIRA_URL_FIELD,
                               JIRA_SHOTGUN_TYPE_FIELD, JIRA_SHOTGUN_ID_FIELD, JIRA_SYNC_IN_FPTR_FIELD)

# TODO:
#  - handle specific sg entities (list for example)/jira values in the `_sync_sg_fields_to_jira` method
#  - find a way to check if a field exist for a specific issue type when accepting SG event
#  - handle Timelog/Note specific workflow

class EntitiesHandler(SyncHandler):
    """
    A handler which syncs a Flow Production Tracking Entities as a Jira Entities.
    """

    __ENTITIES_NOT_FLAGGED_AS_SYNCED = ["Note", "TimeLog"]
    __NOTE_SG_FIELDS = ["subject", "content", "user"]

    def __init__(self, syncer, entity_mapping):
        """
        Instantiate a handler for the given syncer.
        :param syncer: A :class:`~sg_jira.Syncer` instance.
        """
        super(EntitiesHandler, self).__init__(syncer)
        self.__entity_mapping = entity_mapping

    def setup(self):
        """
        Check the Jira and Flow Production Tracking site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """

        self.__jira_sync_in_fptr_field_id = self._jira.get_jira_issue_field_id(JIRA_SYNC_IN_FPTR_FIELD.lower())
        if not self.__jira_sync_in_fptr_field_id:
            raise RuntimeError("Missing required custom Jira field %s" % JIRA_SYNC_IN_FPTR_FIELD)

        for entity_mapping in self.__entity_mapping:

            # check that the FPTR entity has been set in the settings
            if "sg_entity" not in entity_mapping.keys():
                raise RuntimeError("Entity mapping does not contain sg_entity key, please check your settings.")
            self._shotgun.assert_entity(entity_mapping["sg_entity"])

            # for now, we don't support sync at project level
            if entity_mapping["sg_entity"] == "Project":
                raise RuntimeError("Syncing at Project level is not supported.")

            # make sure that the required FPTR fields has been created for the entity
            self._shotgun.assert_field(
                entity_mapping["sg_entity"], SHOTGUN_JIRA_ID_FIELD, "text", check_unique=True
            )

            # for some entities, we need to add extra checks
            if entity_mapping["sg_entity"] not in self.__ENTITIES_NOT_FLAGGED_AS_SYNCED:

                if "jira_issue_type" not in entity_mapping.keys():
                    raise RuntimeError(
                        "Entity mapping does not contain jira_issue_type key, please check your settings."
                    )
                self._jira.issue_type_by_name(entity_mapping["jira_issue_type"])

                self._shotgun.assert_field(
                    entity_mapping["sg_entity"],
                    SHOTGUN_SYNC_IN_JIRA_FIELD,
                    "checkbox"
                )

                # check that the field mapping has been defined in the settings
                if "field_mapping" not in entity_mapping.keys():
                    raise RuntimeError("Entity mapping does not contain field_mapping key, please check your settings.")

                for field_mapping in entity_mapping["field_mapping"]:

                    # check that the FPTR field has correctly been setup and exist in the FPTR schema
                    if "sg_field" not in field_mapping.keys():
                        raise RuntimeError("Field mapping does not contain sg_field key, please check your settings.")
                    self._shotgun.assert_field(
                        entity_mapping["sg_entity"],
                        field_mapping["sg_field"],
                        None
                    )

                    # check that the Jira field exist
                    if "jira_field" not in field_mapping.keys():
                        raise RuntimeError("Field mapping does not contain jira_field key, please check your settings.")
                    self._jira.assert_field(field_mapping["jira_field"])

                    # special use case for the Jira assignee field
                    # it should only be mapped to a FPTR entity/multi-entity HumanUser field
                    if field_mapping["jira_field"] == "assignee":
                        sg_field_schema = self._shotgun.get_field_schema(
                            entity_mapping["sg_entity"],
                            field_mapping["sg_field"]
                        )
                        data_type = sg_field_schema["data_type"]["value"]
                        if data_type not in ["multi_entity", "entity"]:
                            raise ValueError(
                                f"{data_type} field type is not valid for Flow Production Tracking "
                                f"{entity_mapping['sg_entity']}.{field_mapping['sg_field']} assignments. Expected "
                                "entity or multi_entity."
                            )
                        sg_valid_types = sg_field_schema["properties"]["valid_types"]["value"]
                        if "HumanUser" not in sg_valid_types:
                            raise ValueError(
                                f"Flow Production Tracking {entity_mapping['sg_entity']}.{field_mapping['sg_field']} "
                                f"assignment field must accept HumanUser entities but only accepts {sg_valid_types}"
                            )

            # if the user has defined a status mapping, check that everything is correctly setup
            if "status_mapping" in entity_mapping.keys():
                if "sg_field" not in entity_mapping["status_mapping"].keys():
                    raise RuntimeError("Status mapping does not contain sg_field key, please check your settings.")
                if "mapping" not in entity_mapping["status_mapping"].keys():
                    raise RuntimeError("Status mapping does not contain mapping key, please check your settings.")
                # TODO: do we want to check that the status really exist in the two DBs

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Flow Production Tracking Entity.
        :returns: `True if the event is accepted for processing, `False` otherwise.
        """

        # check that the entity linked to the event is supported by the bridge
        if entity_type not in self._supported_shotgun_entities_for_shotgun_event():
            self._logger.debug(
                f"Rejecting Flow Production Tracking event for unsupported PTR entity {entity_type}: {event}"
            )
            return False

        meta = event["meta"]
        field = meta["attribute_name"]

        # check that the field linked to the event is supported by the bridge
        if field not in self._supported_shotgun_fields_for_shotgun_event(entity_type) + [SHOTGUN_SYNC_IN_JIRA_FIELD]:
            self._logger.debug(
                f"Rejecting Flow Production Tracking event for unsupported PTR field {field}: {event}"
            )
            return False

        sg_entity = self._shotgun.find_one(
            entity_type,
            [["id", "is", entity_id]],
            self.__sg_get_entity_fields(entity_type)
        )
        if not sg_entity:
            self._logger.debug(
                f"Rejecting Flow Production Tracking event for unfounded PTR entity {entity_type}: {entity_id}"
            )
            return False

        # for now, we only support project entities as we need to find the associated Jira project
        if not sg_entity.get(f"project.Project.{SHOTGUN_JIRA_ID_FIELD}"):
            self._logger.debug(
                f"Rejecting Flow Production Tracking event because {entity_type} ({entity_id}) doesn't belong to a FPTR"
                f" Project associated to a Jira Project."
            )
            return False

        # check that the entity linked to the event has been flagged as ready-to-sync in FPTR
        # some special entities like Notes or TimeLogs don't need the flag as they are tied to other flagged entities
        if entity_type not in self.__ENTITIES_NOT_FLAGGED_AS_SYNCED and not sg_entity.get(SHOTGUN_SYNC_IN_JIRA_FIELD):
            self._logger.debug(
                f"Rejecting Flow Production Tracking event because {entity_type} ({entity_id}) "
                f"is not flagged as ready-to-sync."
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
        # Special use cases: when a new Note is added to a Task, the "in_create" flag
        # will be propagated to the Task entity as well while it can be an existing Task
        if sg_entity[SHOTGUN_JIRA_ID_FIELD] and meta.get("in_create") and field not in ["open_notes"] :
            self._logger.debug(
                f"Rejecting Flow Production Tracking event for {entity_type}.{field} field update during "
                f"create. Entity was already created in Jira: {event}"
            )
            return False

        # if we're trying to sync a FPTR as a Jira Issue, we need to make sure that the issue type exists in the
        # project and has the required field
        jira_project_key = sg_entity[f"project.Project.{SHOTGUN_JIRA_ID_FIELD}"]
        sync_settings = self.__get_sg_entity_settings(entity_type)
        if entity_type not in self.__ENTITIES_NOT_FLAGGED_AS_SYNCED:

            try:
                self._jira.issue_type_by_name(sync_settings["jira_issue_type"], jira_project_key)
            except KeyError:
                self._logger.debug(
                    f"Rejecting Flow Production Tracking event because issue type {sync_settings['jira_issue_type']} "
                    f"has not been enabled for project {jira_project_key} in Jira: {event}"
                )
                return False

            jira_project = self.get_jira_project(jira_project_key)
            if not jira_project:
                self._logger.debug(
                    f"Rejecting Flow Production Tracking event because project {jira_project_key} doesn't exist in Jira"
                )
                return False

            required_fields = [JIRA_SHOTGUN_ID_FIELD, JIRA_SHOTGUN_TYPE_FIELD]
            jira_fields = self._jira.get_project_issue_type_fields(jira_project, sync_settings["jira_issue_type"])
            for rf in required_fields:
                jira_field_id = self._jira.get_jira_issue_field_id(rf.lower())
                if jira_field_id not in jira_fields.keys():
                    self._logger.debug(
                        f"Rejection Flow Production Tracking event because Jira field {rf} ({jira_field_id}) has not "
                        f"been enabled for Jira Project {jira_project} and Issue Type {sync_settings['jira_issue_type']}""."
                    )
                    return False

        return True

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Flow Production Tracking event for the given Flow Production Tracking Entity
        :param str entity_type: The PTR Entity type to sync.
        :param int entity_id: The id of the PTR Entity to sync.
        :param event: A dictionary with the event for the change.
        :returns: True if the event was successfully processed, False if the
                  sync didn't happen for any reason.
        """

        sg_field = event["meta"]["attribute_name"]

        sg_entity = self._shotgun.consolidate_entity(
            {"type": entity_type, "id": entity_id},
            self.__sg_get_entity_fields(entity_type)
        )

        # if the entity already has an associated Jira ID, make sur to retrieve the associated Jira object
        jira_entity = None
        if sg_entity[SHOTGUN_JIRA_ID_FIELD]:
            jira_entity = self._get_jira_entity(entity_type, entity_id, sg_entity[SHOTGUN_JIRA_ID_FIELD])
            if not jira_entity:
                return False

        jira_project_key = sg_entity[f"project.Project.{SHOTGUN_JIRA_ID_FIELD}"]
        jira_project = self.get_jira_project(jira_project_key)

        # if the entity doesn't exist, create it and then sync all the fields
        if not jira_entity:
            # here, we are assuming that these entities will be created at an upper level
            if sg_entity["type"] in self.__ENTITIES_NOT_FLAGGED_AS_SYNCED:
                return True
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

        # TODO: handle worklog workflow

        if resource_type.lower() != "issue":
            self._logger.debug(
                f"Rejecting Jira event for a {resource_type} Jira resource. Handler only "
                "accepts Issue resources."
            )
            return False

        # Check the event payload and reject the event if we don't have what we
        # expect
        jira_issue = event.get("issue")
        if not jira_issue:
            self._logger.debug(f"Rejecting Jira event without an issue: {event}")
            return False

        webhook_event = event.get("webhookEvent")
        if not webhook_event or webhook_event not in self._supported_jira_webhook_events():
            self._logger.debug(f"Rejecting event with an unsupported webhook event '{webhook_event}': {event}")
            return False

        fields = jira_issue.get("fields")
        if not fields:
            self._logger.debug(f"Rejecting Jira event without issue fields: {event}")
            return False

        jira_project = fields.get("project")
        if not jira_project:
            self._logger.debug(f"Rejecting Jira event without a project: {event}")
            return False

        # check that the Jira project is associated to a FPTR project
        sg_project = self._shotgun.find_one("Project", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_project["key"]]])
        if not sg_project:
            self._logger.debug(
                f"Rejecting Jira event because the Jira Project {jira_project['key']} doesn't have an associated "
                f"Flow Production Tracking project."
            )
            return False

        if "comment" in webhook_event:
            jira_comment = event.get("comment")
            if not jira_comment:
                self._logger.debug(f"Rejecting Jira event without a comment: {event}")
                return False

        else:

            changelog = event.get("changelog")
            if not changelog:
                self._logger.debug(f"Rejecting Jira event without a changelog: {event}")
                return False

            issue_type = fields.get("issuetype")
            if not issue_type:
                self._logger.debug(f"Rejecting Jira event without an issue type: {event}")
                return False

            # check that the issue type has been defined in the settings
            if issue_type["name"] not in self._supported_jira_issue_types_for_jira_event():
                self._logger.debug(f"Rejecting Jira event for unsupported issue type {issue_type}: {event}")
                return False

            # check that the required Jira fields has been enabled for the current project and issue type
            required_fields = [JIRA_SYNC_IN_FPTR_FIELD]
            for rf in required_fields:
                jira_field_id = self._jira.get_jira_issue_field_id(rf.lower())
                if jira_field_id not in fields.keys():
                    self._logger.debug(
                        f"Rejecting Jira event because Jira field {rf} ({jira_field_id}) has not "
                        f"been enabled for Jira Project {jira_project['key']} and Issue Type {issue_type['name']}."
                    )
                    return False

            # check that the Issue is flagged as synced
            if not fields.get(self.__jira_sync_in_fptr_field_id):
                self._logger.debug(f"Rejecting Jira event because Jira Issue {jira_issue['key']} has not been flagged as synced.")
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


        webhook_event = event["webhookEvent"]

        if "comment" in  webhook_event:
            return self._sync_jira_comment_to_sg(event)

        jira_issue = self._jira.issue(event["issue"]["key"])

        sg_type = getattr(jira_issue.fields, self._jira.jira_shotgun_type_field)
        sg_id = getattr(jira_issue.fields, self._jira.jira_shotgun_id_field)
        if sg_id and not sg_id.isdigit():
            raise ValueError(f"Invalid Flow Production Tracking id {sg_id}, it must be an integer")

        # if we have FPTR information, check that the entity exists in FPTR
        sg_entity = None
        if sg_id and sg_type:
            sg_entity = self._shotgun.consolidate_entity({"type": sg_type, "id": int(sg_id)})
            if not sg_entity:
                self._logger.info(f"Invalid Flow Production Tracking entity {sg_type} ({sg_id}))")
                return False

        if not sg_entity:
            sg_entity = self._create_sg_entity(jira_issue)

        jira_fields = []
        supported_jira_fields = (self._supported_jira_fields_for_jira_event(jira_issue.fields.issuetype.name) +
                                 [self.__jira_sync_in_fptr_field_id])
        for change in event["changelog"]["items"]:
            # Depending on the Jira server version, we can get the Jira field id
            # in the change payload or just the field name.
            # If we don't have the field id, retrieve it from our internal mapping.
            jira_field_id = change.get("fieldId") or self._jira.get_jira_issue_field_id(change["field"])
            if jira_field_id not in supported_jira_fields:
                self._logger.debug( f"Rejecting Jira event for unsupported field {jira_field_id}: {event}")
                continue
            jira_fields.append(jira_field_id)

        if self.__jira_sync_in_fptr_field_id in jira_fields:
            return self._sync_jira_fields_to_sg(jira_issue, sg_entity)

        return self._sync_jira_fields_to_sg(jira_issue, sg_entity, jira_fields)


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
        :returns: A list of strings.
        """

        if entity_type == "Note":
            return self.__NOTE_SG_FIELDS

        sg_fields = []
        for entity_mapping in self.__entity_mapping:
            if entity_mapping["sg_entity"] == entity_type:
                sg_fields = [m["sg_field"]for m in entity_mapping["field_mapping"]]
            if entity_mapping.get("status_mapping"):
                sg_fields.append(entity_mapping["status_mapping"]["sg_field"])
        return sg_fields

    def _supported_jira_webhook_events(self):
        """"""
        return [
            "jira:issue_created",
            "jira:issue_updated",
            # "comment_created",
            "comment_updated",
            "jira:worklog_created",
            "jira:worklog_updated",
        ]

    def _supported_jira_issue_types_for_jira_event(self):
        """"""
        return [m["jira_issue_type"] for m in self.__entity_mapping]

    def _supported_jira_fields_for_jira_event(self, issue_type):
        """"""
        jira_fields = []
        for entity_mapping in self.__entity_mapping:
            if entity_mapping["jira_issue_type"] == issue_type:
                jira_fields = [m["jira_field"]for m in entity_mapping["field_mapping"]]
        return jira_fields

    def __sg_get_entity_fields(self, entity_type):
        """Get all the FPTR fields required when querying the database"""
        return [
            SHOTGUN_SYNC_IN_JIRA_FIELD,
            SHOTGUN_JIRA_ID_FIELD,
            "project",
            f"project.Project.{SHOTGUN_JIRA_ID_FIELD}",
            "created_by"
        ] + self._supported_shotgun_fields_for_shotgun_event(entity_type)

    def __get_sg_entity_settings(self, entity_type):
        """Returns the sync settings for the given entity type"""
        for entity_mapping in self.__entity_mapping:
            if entity_mapping["sg_entity"] == entity_type:
                return entity_mapping
        return None

    def __get_jira_issue_type_settings(self, issue_type):
        """"""
        for entity_mapping in self.__entity_mapping:
            if entity_mapping["jira_issue_type"] == issue_type:
                return entity_mapping
        return None

    def __get_field_mapping(self, entity_type, jira_field=None, sg_field=None):
        """"""
        if not jira_field and not sg_field:
            raise ValueError("jira_field or sg_field must be provided")

        if jira_field and sg_field:
            raise ValueError("Only jira_field or sg_field must be provided, but not both of them")

        entity_mapping = self.__get_sg_entity_settings(entity_type)

        # special use cases for the status fields
        if jira_field and jira_field == "status" and entity_mapping["status_mapping"]:
            return {
                "sg_field": entity_mapping["status_mapping"]["sg_field"],
                "jira_field": "status",
                "sync_direction": entity_mapping["status_mapping"].get("sync_direction", "both_way")
            }

        if sg_field and entity_mapping["status_mapping"] and sg_field == entity_mapping["status_mapping"]["sg_field"]:
            return {
                "sg_field": sg_field,
                "jira_field": "status",
                "sync_direction": entity_mapping["status_mapping"].get("sync_direction", "both_way")
            }

        for f in entity_mapping["field_mapping"]:
            if jira_field and f["jira_field"] == jira_field:
                return f
            elif sg_field and f["sg_field"] == sg_field:
                return f

    def __get_status_mapping(self, entity_type, sg_status=None, jira_status=None):
        """"""
        if not sg_status and not jira_status:
            raise ValueError("sg_status or jira_status must be provided")

        if sg_status and jira_status:
            raise ValueError("Only sg_status or jira_status must be provided, but not both of them")

        entity_mapping = self.__get_sg_entity_settings(entity_type)
        for s_status, j_status in entity_mapping["status_mapping"]["mapping"].items():
            if sg_status and sg_status == s_status:
                return j_status
            elif jira_status and j_status == jira_status:
                return s_status

    def _get_jira_entity(self, entity_type, entity_id, jira_key):
        """Get the Jira object for the given Jira entity ID and entity type."""

        # we need to manage special entities like Note/Comment and TimeLog/Worklog apart
        if entity_type == "Note":
            jira_issue_key, jira_comment_id = self.__parse_jira_key_from_sg_entity(entity_type, jira_key)
            return self._get_jira_issue_comment(jira_issue_key, jira_comment_id)

        # TODO: implement the logic for the Timelogs
        elif entity_type == "TimeLog":
            return

        # for all other entities, we consider them as Jira issues
        else:
            jira_issue = self.get_jira_issue(jira_key)
            if not jira_issue:
                self._logger.warning(
                    f"Unable to find Jira Issue {jira_key} associated to the FPTR {entity_type} ({entity_id})"
                )
                return
            # once the issue has been found, make sure it is linked to the right FPTR entity
            jira_sg_id = int(getattr(jira_issue.fields, self._jira.jira_shotgun_id_field))
            jira_sg_type = getattr(jira_issue.fields, self._jira.jira_shotgun_type_field)
            if jira_sg_id != entity_id or jira_sg_type != entity_type:
                self._logger.warning(
                    f"Bad Jira Issue {jira_issue}. Expected it to be linked to Flow Production Tracking "
                    f"{entity_type} ({entity_id}) but instead it is linked to Flow Production Tracking {jira_sg_type} "
                    f"({jira_sg_id})."
                )
                return
            return jira_issue

    def _create_jira_entity(self, sg_entity, jira_project):
        """"""

        jira_entity = None

        # we need to manage special entities like Note/Comment and TimeLog/Worklog apart
        # TODO: implement the logic for the Notes
        if sg_entity["type"] == "Note":
            return

        # TODO: implement the logic for the Timelogs
        elif sg_entity["type"] == "TimeLog":
            return

        # Considering all the other FPTR entities as Jira issues
        else:

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
            summary_field = self.__get_field_mapping(sg_entity["type"], jira_field="summary")
            if summary_field:
                summary_field = summary_field["sg_field"]
            else:
                summary_field = self._shotgun.get_entity_name_field(sg_entity["type"])

            shotgun_url = self._shotgun.get_entity_page_url(sg_entity)

            self._logger.info(
                f"Creating Jira Issue in Project {jira_project} for Flow Production Tracking {sg_entity['type']} "
                f"{sg_entity['name']} ({sg_entity['id']})"
            )

            entity_settings = self.__get_sg_entity_settings(sg_entity["type"])
            sync_in_fptr = "False" if entity_settings.get("sync_direction", "both_way") == "sg_to_jira" else "True"
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

        # update FPTR with the Jira data
        if jira_entity:
            sg_data = {
                SHOTGUN_JIRA_ID_FIELD: jira_entity.key,
            }
            if isinstance(jira_entity, jira.resources.Issue):
                sg_data[SHOTGUN_JIRA_URL_FIELD] = {
                    "url": jira_entity.permalink(),
                    "name": "View in Jira",
                }
            self._shotgun.update(sg_entity["type"], sg_entity["id"], sg_data)

        return jira_entity

    def _sync_sg_fields_to_jira(self, sg_entity, jira_entity, field_name=None):
        """"""

        jira_fields = {}
        sync_with_errors = False

        # Notes have a special behavior
        if sg_entity["type"] == "Note":
            comment_body = self._hook.compose_jira_comment_body(sg_entity)
            jira_entity.update(body=comment_body)
            return True

        # if no field name is supplied, that means we want to sync all the fields so get them
        if not field_name:
            sg_fields = self._supported_shotgun_fields_for_shotgun_event(sg_entity["type"])
        else:
            sg_fields = [field_name]

        # query Jira to get all the editable fields for the current issue type
        editable_jira_fields = self._jira.get_jira_issue_edit_meta(jira_entity)

        for sg_field in sg_fields:

            field_mapping = self.__get_field_mapping(sg_entity["type"], sg_field=sg_field)

            if field_mapping.get("sync_direction") == "jira_to_sg":
                continue

            # get the associated Jira field
            jira_field = field_mapping["jira_field"]

            if jira_field == "watches":
                self._sync_sg_watchers_to_jira(sg_entity[sg_field], jira_entity)
                continue

            if jira_field == "status":
                self._sync_sg_status_to_jira(sg_entity[sg_field], sg_entity["type"], jira_entity)
                continue

            if jira_field == "comment":
                self._sync_sg_notes_to_jira(sg_entity[sg_field], sg_entity["type"], jira_entity)
                continue

            # check that we have permission to edit this field
            if jira_field not in editable_jira_fields:
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
                        editable_jira_fields[jira_field]
                    )
                else:
                    jira_value = self._hook.get_jira_value_from_sg_value(
                        sg_entity[sg_field],
                        jira_entity,
                        jira_field,
                        editable_jira_fields[jira_field]
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
            jira_entity.update(fields=jira_fields)

        return sync_with_errors

    def _sync_sg_watchers_to_jira(self, sg_value, jira_issue):
        """"""

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

                jira_user = self._jira.find_jira_user(sg_user["email"], jira_issue=jira_issue)
                if jira_user:
                    current_watchers.append(jira_user.accountId)
                    self._logger.debug(f"Adding {jira_user.displayName} to {jira_issue} watchers list.")
                    # add_watcher method supports both user_id and accountId properties
                    self._jira.add_watcher(jira_issue, jira_user.accountId)

        # now, go through all watchers and remove the one that are not in FPTR anymore
        for jira_watcher in self._jira.watchers(jira_issue).watchers:
            if jira_watcher.accountId not in current_watchers:
                self._logger.debug(f"Removing {jira_watcher.displayName} from {jira_issue} watchers list.")
                # In older versions of the client (<= 3.0) we used jira_user.user_id
                # However, newer versions of the remove_watcher method supports name search
                self._jira.remove_watcher(jira_issue, jira_watcher.displayName)

        return True

    def _sync_sg_status_to_jira(self, sg_value, entity_type, jira_issue):
        """"""

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
            f"Updated from Flow Production Tracking {entity_type} moving to {sg_value}"
        )

    def _sync_sg_notes_to_jira(self, sg_value, entity_type, jira_issue):
        """"""

        sg_fields = ["subject", "content", "user", SHOTGUN_JIRA_ID_FIELD]

        for n in sg_value:

            jira_comment = None
            sg_note = self._shotgun.consolidate_entity(
                {"type": n["type"], "id": n["id"]},
                sg_fields
            )

            # the note doesn't have an associated Jira ID, we need to create the comment in Jira
            if not sg_note[SHOTGUN_JIRA_ID_FIELD]:
                self._logger.debug(f"Adding FPTR Note ({sg_note['id']}) as comment for Jira issue {jira_issue}")
                jira_comment = self._create_jira_comment(jira_issue, sg_note)

            else:
                jira_issue_key, jira_comment_id = self.__parse_jira_key_from_sg_entity(sg_note["type"], sg_note[SHOTGUN_JIRA_ID_FIELD])
                if jira_issue_key != jira_issue.key:
                    self._logger.debug(
                        f"FPTR Note ({sg_note['id']}) is already associated with Jira issue {jira_issue_key}, "
                        f"skipping its update."
                    )
                    continue

                jira_comment = self._get_jira_issue_comment(jira_issue_key, jira_comment_id)
                if not jira_comment:
                    self._logger.debug(
                        f"FPTR Note ({sg_note['id']}) was associated with Jira comment ({jira_comment_id}) on Jira Issue "
                        f"{jira_issue_key} which no longer exists. A new comment will be created."
                    )
                    jira_comment = self._create_jira_comment(jira_issue, sg_note)

        # TODO: remove the Jira comments that do no longer exist in FPTR

    def _create_sg_entity(self, jira_issue):
        """"""

        entity_mapping = self.__get_jira_issue_type_settings(jira_issue.fields.issuetype.name)

        sg_entity_name_field = self._shotgun.get_entity_name_field(entity_mapping["sg_entity"])
        jira_name_field = self.__get_field_mapping(entity_mapping["sg_entity"], sg_field=sg_entity_name_field)
        if jira_name_field:
            jira_name_field = jira_name_field["jira_field"]
        else:
            jira_name_field = "summary"

        sg_project = self._shotgun.find_one("Project", [[SHOTGUN_JIRA_ID_FIELD, "is", jira_issue.fields.project.key]])
        sync_in_jira = False if entity_mapping.get("sync_direction", "both_way") == "jira_to_sg" else True

        sg_data = {
            sg_entity_name_field: getattr(jira_issue.fields, jira_name_field),
            SHOTGUN_JIRA_ID_FIELD: jira_issue.key,
            SHOTGUN_SYNC_IN_JIRA_FIELD: sync_in_jira,
            "project": sg_project
        }

        sg_entity = self._shotgun.create(entity_mapping["sg_entity"], sg_data)

        # update Jira with the FPTR entity data
        jira_fields = {
            self._jira.jira_shotgun_type_field: sg_entity["type"],
            self._jira.jira_shotgun_id_field: str(sg_entity["id"])
        }
        jira_issue.update(fields=jira_fields)

        return sg_entity

    def _sync_jira_comment_to_sg(self, event):
        """"""

        sg_jira_key = "%s/%s" % (event["issue"]["key"], event["comment"]["id"])
        sg_notes = self._shotgun.find(
            "Note",
            [[SHOTGUN_JIRA_ID_FIELD, "is", sg_jira_key]],
            fields=["subject", "tasks"],
        )

        # If we have more than one Note with the same key, we don't want to
        # create more mess.
        if len(sg_notes) > 1:
            self._logger.warning(
                f"Unable to process Jira Comment {event} event. More than one Note "
                f"exists in Shotgun with Jira key {sg_jira_key}: {sg_notes}"
            )
            return False

        # TODO: We don't know if the Issue this comment is for, is currently
        #       synced to Shotgun. We need to load it first to properly check
        #       if this is a warning or debug level message, but that's
        #       expensive. Keeping it at debug for now.
        if not sg_notes:
            self._logger.debug(
                f"Unable to process Jira Comment {event} event. Unable to find a Shotgun "
                f"Note with Jira key {sg_jira_key}"
            )
            return False

        # We have a single Note
        # TODO: Check that the Task the Note is linked to has syncing enabled.
        #       Otherwise syncing could be turned off for the Task but this
        #       will still sync the Note.

        sg_data = {}
        try:
            sg_data["subject"], sg_data["content"], sg_data["user"] = self._hook.compose_sg_note(event["comment"]["body"])
        except InvalidJiraValue as e:
            self._logger.warning(f"Unable to process Jira Comment {event} event. {e}")
            return False

        self._logger.debug(f"Updating FPTR Note ({sg_notes[0]['id']}) (jira_key {sg_jira_key}) with data {sg_data}")

        self._shotgun.update("Note", sg_notes[0]["id"], sg_data)
        return True

    def _sync_jira_fields_to_sg(self, jira_issue, sg_entity, jira_fields=None):
        """"""

        sync_with_errors = False

        issue_type = jira_issue.fields.issuetype.name

        if not jira_fields:
            jira_fields = self._supported_jira_fields_for_jira_event(issue_type)

        sg_data = {}

        for jira_field in jira_fields:

            field_mapping = self.__get_field_mapping(sg_entity["type"], jira_field=jira_field)

            if field_mapping.get("sync_direction") == "sg_to_jira":
                continue

            # get the associated FPTR field
            sg_field = field_mapping["sg_field"]

            # make sure the FPTR field is editable
            sg_field_schema = self._shotgun.get_field_schema(sg_entity["type"], sg_field)
            if not sg_field_schema["editable"]["value"]:
                self._logger.warning(
                    f"Not syncing Jira {issue_type}.{jira_field} to Flow Production Tracking . "
                    f"Target Flow Production Tracking {sg_entity['type']}.{sg_field} field is not editable"
                )
                sync_with_errors = True
                continue

            jira_value = getattr(jira_issue.fields, jira_field)
            sg_value = None

            # TODO: manage Jira watchers
            if jira_field == "watches":
                continue

            # TODO: manage SG status field
            elif sg_field_schema["data_type"]["value"] == "status_list":
                sg_value = self.__get_status_mapping(sg_entity["type"], jira_status=jira_value) if jira_value else None

            else:
                try:
                    sg_value = self._hook.get_sg_value_from_jira_value(jira_value, sg_entity["project"], sg_field_schema)
                except Exception as e:
                    self._logger.warning(
                        f"Not syncing Jira {issue_type}.{jira_field} to Flow Production Tracking . "
                        f"Error occurred when trying to convert FPTR value to Jira value: {e}"
                    )
                    sync_with_errors = True
                    continue

            sg_data[sg_field] = sg_value

        if sg_data:
            self._shotgun.update(sg_entity["type"], sg_entity["id"], sg_data)

        return sync_with_errors

    def _create_jira_comment(self, jira_issue, sg_note):
        """"""

        jira_comment = self._jira.add_comment(
            jira_issue,
            self._hook.compose_jira_comment_body(sg_note),
            visibility=None,  # TODO: check if Note properties should drive this
            is_internal=False,
        )
        # update the FPTR Note with the comment ID
        comment_key = "%s/%s" % (jira_issue.key, jira_comment.id)
        self._shotgun.update(
            sg_note["type"],
            sg_note["id"],
            {SHOTGUN_JIRA_ID_FIELD: comment_key}
        )

        return jira_comment

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

    @staticmethod
    def __parse_jira_key_from_sg_entity(sg_entity_type, jira_key):
        """"""

        if sg_entity_type not in ["Note"]:
            return jira_key, None

        parts = jira_key.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(
                f"Invalid Jira key {jira_key}, it must be in the format "
                "'<jira issue key>/<jira entity id>'"
            )
        return parts[0], parts[1]
