# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from sg_jira.handlers import SyncHandler
from sg_jira.constants import SHOTGUN_SYNC_IN_JIRA_FIELD, SHOTGUN_JIRA_ID_FIELD, JIRA_SHOTGUN_TYPE_FIELD, JIRA_SHOTGUN_ID_FIELD


class EntitiesHandler(SyncHandler):
    """
    A handler which syncs a Flow Production Tracking Entities as a Jira Entities.
    """

    __ENTITIES_NOT_FLAGGED_AS_SYNCED = ["Note", "TimeLog"]

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
                if "name" not in field_mapping["sg_field"].keys() or "type" not in field_mapping["sg_field"].keys():
                    raise RuntimeError("Field mapping does not contain name or type key, please check your settings.")
                self._shotgun.assert_field(
                    entity_mapping["sg_entity"],
                    field_mapping["sg_field"]["name"],
                    field_mapping["sg_field"]["type"]
                )

                # check that the Jira field exist
                if "jira_field" not in field_mapping.keys():
                    raise RuntimeError("Field mapping does not contain jira_field key, please check your settings.")
                self._jira.assert_field(field_mapping["jira_field"])

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
        if sg_entity[SHOTGUN_JIRA_ID_FIELD] and meta.get("in_create"):
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
            jira_fields = self._jira.get_project_issue_fields(jira_project, sync_settings["jira_issue_type"])
            for rf in required_fields:
                jira_field_id = self._jira.get_jira_issue_field_id(rf.lower())
                if jira_field_id not in jira_fields.keys():
                    self._logger.debug(
                        f"Rejection Flow Production Tracking event because Jira field {rf} ({jira_field_id}) has not "
                        f"been enabled for Jira Project {jira_project}."
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
                return

        jira_project_key = sg_entity[f"project.Project.{SHOTGUN_JIRA_ID_FIELD}"]
        jira_project = self.get_jira_project(jira_project_key)

        # if the entity doesn't exist, create it
        if not jira_entity:
            jira_entity = self._create_jira_entity(sg_entity, jira_project)

        # in case the sync checkbox has been triggered in FPTR, we want to perform a full sync of the entity
        if sg_field == SHOTGUN_SYNC_IN_JIRA_FIELD:
            self._sync_sg_fields_to_jira(sg_entity, jira_entity)
        # otherwise, we just want to sync the specific field
        else:
            self._sync_sg_fields_to_jira(sg_entity, jira_entity, field_name=sg_field)

        return True

    def accept_jira_event(self, resource_type, resource_id, event):
        """
        Accept or reject the given event for the given Jira resource.
        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event is accepted for processing, False otherwise.
        """
        self._logger.info("[DEBUG BARBARA] Entering accept_jira_event()...")
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
        self._logger.info("[DEBUG BARBARA] Entering process_jira_event()...")
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
        :returns: A list of strings.
        """
        for entity_mapping in self.__entity_mapping:
            if entity_mapping["sg_entity"] == entity_type:
                return [m["sg_field"]["name"] for m in entity_mapping["field_mapping"]]
        return []

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

    def __get_field_mapping(self, entity_type, jira_field=None, sg_field=None):
        """"""
        if not jira_field and not sg_field:
            raise ValueError("jira_field or sg_field must be provided")

        if jira_field and sg_field:
            raise ValueError("Only jira_field or sg_field must be provided, but not both of them")

        entity_mapping = self.__get_sg_entity_settings(entity_type)
        for f in entity_mapping["field_mapping"]:
            if jira_field and f["jira_field"] == jira_field:
                return f
            elif sg_field and f["sg_field"] == sg_field:
                return f

    def _get_jira_entity(self, entity_type, entity_id, jira_key):
        """Get the Jira object for the given Jira entity ID and entity type."""

        # we need to manage special entities like Note/Comment and TimeLog/Worklog apart
        # TODO: implement the logic for the Notes
        if entity_type == "Note":
            return

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
                summary_field = summary_field["sg_field"]["name"]
            else:
                summary_field = self._shotgun.get_entity_name_field(sg_entity["type"])

            self._logger.info(
                f"Creating Jira Issue in Project {jira_project} for Flow Production Tracking {sg_entity['type']} "
                f"{sg_entity['name']} ({sg_entity['id']})"
            )

            data = {
                "project": jira_project.raw,
                "summary": sg_entity[summary_field].replace("\n", "").replace("\r", ""),
                "description": "",
                self._jira.jira_shotgun_id_field: str(sg_entity["id"]),
                self._jira.jira_shotgun_type_field: sg_entity["type"],
                # self._jira.jira_shotgun_url_field: shotgun_url,
                "reporter": reporter,
            }
            issue_type = self.__get_sg_entity_settings(sg_entity["type"])["jira_issue_type"]
            jira_entity = self._jira.create_issue_from_data(
                jira_project,
                issue_type,
                data,
            )

        # update FPTR with the Jira data
        self._shotgun.update(
            sg_entity["type"],
            sg_entity["id"],
            {
                SHOTGUN_JIRA_ID_FIELD: jira_entity.key,
                # SHOTGUN_JIRA_URL_FIELD: {
                #     "url": jira_issue.permalink(),
                #     "name": "View in Jira",
                # },
            },
        )

        return jira_entity

    def _sync_sg_fields_to_jira(self, sg_entity, jira_issue, field_name=None):
        """"""

        # if no field name is supplied, that means we want to sync all the fields so get them
        if not field_name:
            sg_fields = self._supported_shotgun_fields_for_shotgun_event(sg_entity["type"])
        else:
            sg_fields = [field_name]

        for sg_field in sg_fields:

            # TODO: handle specific sg entities (list for example)
            pass

