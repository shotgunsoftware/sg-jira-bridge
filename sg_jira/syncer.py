# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import logging
from jira import JIRAError
import jira

from .errors import UnsuitableShotgunValue, UnsuitableJiraValue


class Syncer(object):
    """
    A class handling syncing between Shotgun and Jira
    """

    def __init__(self, name, bridge, **kwargs):
        """
        Instatiate a new syncer for the given bridge.

        :param str name: A unique name for the syncer.
        :param bridge: A :class:`sg_jira.Bridge` instance.
        """
        super(Syncer, self).__init__()
        self._name = name
        self._bridge = bridge
        # Set a logger per instance: this allows to filter logs with the
        # syncer name, or even have log file handlers per syncer
        self._logger = logging.getLogger(__name__).getChild(self._name)

    @property
    def bridge(self):
        """
        Returns the :class:`sg_jira.Bridge` instance used by this syncer.
        """
        return self._bridge

    @property
    def shotgun(self):
        """
        Return a connected Shotgun handle.
        """
        return self._bridge.shotgun

    @property
    def jira(self):
        """
        Return a connected Jira handle.
        """
        return self._bridge.jira

    @property
    def sg_jira_statuses_mapping(self):
        """
        Needs to be re-implemented in deriving classes and return a dictionary
        where keys are Shotgun status short codes and values Jira Issue status
        names.
        """
        raise NotImplementedError

    def supported_shotgun_fields(self, shotgun_entity_type):
        """
        Needs to be re-implemented in deriving classes and return the list of
        Shotgun fields that the syncer can process for the given Shotgun Entity
        type.
        """
        raise NotImplementedError

    def setup(self):
        """
        Check the Jira and Shotgun site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """
        pass

    def get_jira_project(self, project_key):
        """
        Retrieve the Jira Project with the given key, if any.

        :returns: A :class:`jira.resources.Project` instance or None.
        """
        for jira_project in self._bridge.jira.projects():
            if jira_project.key == project_key:
                return jira_project
        return None

    def get_jira_issue(self, issue_key):
        """
        Retrieve the Jira Issue with the given key, if any.

        :param str issue_key: A Jira Issue key to look for.
        :returns: A :class:`jira.resources.Issue` instance or None.
        :raises: RuntimeError if the Issue if not bound to any Project.
        """
        jira_issue = None
        try:
            jira_issue = self.jira.issue(issue_key)
            if not jira_issue.fields.project:
                # This should never happen as it does not seem possible to
                # have Issues not linked to a project. Report the error if it
                # does happen.
                raise RuntimeError(
                    "Jira Issue %s is not bound to any Project." % issue_key
                )
        except JIRAError as e:
            # Jira raises a 404 error if it can't find the Issue: catch the
            # error and let the method return None in that case.
            if e.status_code == 404:
                pass
            else:
                raise
        return jira_issue

    def get_jira_issue_edit_meta(self, jira_issue):
        """
        Return the edit metadata for the given Jira Issue.

        :param jira_issue: A :class:`jira.resources.Issue`.
        :returns: The Jira Issue edit metadata `fields` property.
        :raises: RuntimeError if the edit metadata can't be retrieved for the
                 given Issue.
        """
        # Retrieve edit meta data for the issue
        # TODO: cache the retrieved data to avoid multiple requests to the server
        edit_meta_data = self.jira.editmeta(jira_issue)
        jira_edit_fields = edit_meta_data.get("fields")
        if not jira_edit_fields:
            raise RuntimeError(
                "Unable to retrieve edit meta data for %s %s. " % (
                    jira_issue.fields.issuetype,
                    jira_issue.key
                )
            )
        return jira_edit_fields

    def create_jira_issue_for_entity(
        self,
        sg_entity,
        jira_project,
        issue_type,
        summary,
        description=None,
        **properties
    ):
        """
        Create a Jira issue linked to the given Shothgun Entity with the given properties

        :param sg_entity: A Shotgun Entity dictionary.
        :param jira_project: A :class:`jira.resources.Project` instance.
        :param str issue_type: The target Issue type name.
        :param str summary: The Issue summary.
        :param str description: An optional description for the Issue.
        :param properties: Arbitrary properties to set on the Jira Issue.
        :returns: A :class:`jira.resources.Issue` instance.
        """
        jira_issue_type = self.jira.issue_type_by_name(issue_type)
        # Retrieve creation meta data for the project / issue type
        # Note: there is a new simpler Project type in Jira where createmeta is not
        # available.
        # https://confluence.atlassian.com/jirasoftwarecloud/working-with-agility-boards-945104895.html
        # https://community.developer.atlassian.com/t/jira-cloud-next-gen-projects-and-connect-apps/23681/14
        # It seems a Project `simplified` key can help distinguish between old
        # school projects and new simpler projects.
        # TODO: cache the retrieved data to avoid multiple requests to the server
        create_meta_data = self.jira.createmeta(
            jira_project,
            issuetypeIds=jira_issue_type.id,
            expand="projects.issuetypes.fields"
        )
        # We asked for a single project / single issue type, so we can just pick
        # the first entry, if it exists.
        if not create_meta_data["projects"] or not create_meta_data["projects"][0]["issuetypes"]:
            self._logger.debug("Create meta data: %s" % create_meta_data)
            raise RuntimeError(
                "Unable to retrieve create meta data for Project %s Issue type %s."  % (
                    jira_project,
                    jira_issue_type.id,
                )
            )
        fields_createmeta = create_meta_data["projects"][0]["issuetypes"][0]["fields"]

        # Retrieve the reporter, either the user who created the Entity or the
        # Jira user used to run the syncing.
        reporter_name = self.jira.current_user()
        created_by = sg_entity["created_by"]
        if created_by["type"] == "HumanUser":
            user = self.consolidate_shotgun_entity(created_by)
            if user:
                user_email = user["email"]
                jira_user = self.find_jira_user(
                    user_email,
                    jira_project=jira_project,
                )
                # If we found a Jira user, use his name as the reporter name,
                # otherwise use the reporter name retrieve from the user used
                # to run the bridge.
                if jira_user:
                    reporter_name = jira_user.name
        else:
            self._logger.debug(
                "Ignoring created by %s which is not a HumanUser." % created_by
            )

        shotgun_url = "%s/detail/%s/%d" % (
            self.shotgun.base_url, sg_entity["type"], sg_entity["id"]
        )

        # Note that JIRA raises an error if there are new line characters in the
        # summary for an Issue or if the description field is not set.
        if description is None:
            description = ""
        data = {
            "project": jira_project.raw,
            "summary": summary.replace("\n", "").replace("\r", ""),
            "description": description,
            self.bridge.jira_shotgun_id_field: "%d" % sg_entity["id"],
            self.bridge.jira_shotgun_type_field: sg_entity["type"],
            self.bridge.jira_shotgun_url_field: shotgun_url,
            "issuetype": jira_issue_type.raw,
            "reporter": {"name": reporter_name},
        }
        # TODO: Treat additional properties
        # Check if we are missing any required data which does not have a default
        # value.
        missing = []
        for k, jira_create_field in fields_createmeta.iteritems():
            if k not in data:
                if jira_create_field["required"] and not jira_create_field["hasDefaultValue"]:
                    missing.append(jira_create_field["name"])
        if missing:
            raise ValueError(
                "The following data is missing in order to create a Jira %s Issue: %s" % (
                    data["issuetype"]["name"],
                    missing,
                )
            )
        # Check if we're trying to set any value which can't be set and validate
        # empty values.
        invalid_fields = []
        data_keys = data.keys() # Retrieve all keys so we can delete them in the dict
        for k in data_keys:
            # Filter out anything which can't be used in creation.
            if k not in fields_createmeta:
                self._logger.warning(
                    "Disabling %s in issue creation which can't be set in Jira" % k
                )
                del data[k]
            elif not data[k] and fields_createmeta[k]["required"]:
                # Handle required fields with empty value
                if fields_createmeta[k]["hasDefaultValue"]:
                    # Empty field data which Jira will set default values for should be removed in
                    # order for Jira to properly set the default. Jira will complain if we leave it
                    # in.
                    self._logger.info(
                        "Removing %s from data payload since it has an empty value. Jira will "
                        "now set a default value." % k
                    )
                    del data[k]
                else:
                    # Empty field data isn't valid if the field is required and doesn't have a
                    # default value in Jira.
                    invalid_fields.append(k)
        if invalid_fields:
            raise ValueError(
                "Unable to create Jira Issue: The following fields are required and cannot "
                "be empty: %s" % invalid_fields
            )

        self._logger.info("Creating Jira issue for %s with %s" % (
            sg_entity, data
        ))

        return self.jira.create_issue(fields=data)

    def get_jira_issue_field_for_shotgun_field(self, shotgun_entity_type, shotgun_field):
        """
        Needs to be re-implemented in deriving classes and return the Jira Issue
        field id to use to sync the given Shotgun Entity type field.

        :returns: A string or `None`.
        """
        raise NotImplementedError

    def get_jira_value_for_shotgun_list_changes(
        self,
        jira_project,
        jira_issue,
        jira_field,
        jira_field_schema,
        shotgun_added,
        shotgun_removed,
    ):
        """
        Handle a Shotgun list value modification and return a Jira value
        corresponding to changes for the given Issue field.

        :param jira_project: A :class:`jira.resources.Project` instance.
        :param jira_issue: A :class:`jira.resources.Issue` instance.
        :param jira_field: A Jira field id, as a string.
        :param jira_field_schema: The jira create or edit meta data for the given
                                  field.
        :param shotgun_added: A list of Shotgun added values.
        :param shotgun_removed: A list of Shotgun removed values.
        """
        current_value = getattr(jira_issue.fields, jira_field)
        is_array = jira_field_schema["schema"]["type"] == "array"

        if is_array:
            if current_value:
                for removed in shotgun_removed:
                    value = self.get_jira_value_for_shotgun_value(
                        jira_project,
                        jira_issue,
                        jira_field,
                        jira_field_schema,
                        removed,
                    )
                    if value in current_value:
                        current_value.remove(value)
                    else:
                        self._logger.debug(
                            "Unable to remove %s mapped to %s from current Jira value %s" % (
                                removed,
                                value,
                                current_value,
                            )
                        )

            for added in shotgun_added:
                value = self.get_jira_value_for_shotgun_value(
                    jira_project,
                    jira_issue,
                    jira_field,
                    jira_field_schema,
                    added,
                )
                if value and value not in current_value:
                    current_value.append(value)
            return current_value
        else:
            # Check if the current value was set to one of the values which were
            # removed. If so, set the value from the added values (if any)
            if current_value:
                for removed in shotgun_removed:
                    value = self.get_jira_value_for_shotgun_value(
                        jira_project,
                        jira_issue,
                        jira_field,
                        jira_field_schema,
                        removed,
                    )
                    if value == current_value:
                        # Unset the current value so the code below will try to
                        # update the value.
                        current_value = None
                        break
                else:
                    self._logger.debug(
                        "Current Jira value %s unaffected by %s removal." % (
                            current_value,
                            shotgun_removed,
                        )
                    )

            if not current_value and shotgun_added:
                # Problem: we might have multiple values in Shotgun but can only set
                # a single one in Jira, so we have to arbitrarily pick one if we
                # have multiple values.
                for sg_value in shotgun_added:
                    self._logger.debug("Treating %s" % sg_value)
                    value = self.get_jira_value_for_shotgun_value(
                        jira_project,
                        jira_issue,
                        jira_field,
                        jira_field_schema,
                        sg_value,
                    )
                    if value:
                        current_value = value
                        added_count = len(shotgun_added)
                        if added_count > 1:
                            self._logger.warning(
                                "Only a single value is accepted by Jira, got "
                                "%d values, using %s mapped to %s" % (
                                    added_count,
                                    sg_value,
                                    current_value
                                )
                            )
                        break
        # Return the modified current value
        return current_value

    def consolidate_shotgun_entity(self, shotgun_entity, fields=None):
        """
        Consolidate the given Shotgun Entity: collect additional field values,
        ensure the Entity name is available under a "name" key.

        :param shotgun_entity: A Shotgun Entity dictionary with at least its id
                               and its type.
        :param fields: An optional list of fields to add to the query.
        :returns: The consolidated Shotgun Entity or `None` if it can't be retrieved.
        """

        # Define the fields we need to handle the Entity type.
        needed_fields = []
        entity_type = shotgun_entity["type"]
        name_field = self.bridge.get_sg_entity_name_field(entity_type)

        if entity_type == "HumanUser":
            needed_fields = [name_field, "email"]
        elif entity_type == "Task":
            needed_fields = [name_field, "task_assignees"]
        else:
            needed_fields = [name_field]

        if self.is_project_shotgun_entity(shotgun_entity["type"]):
            needed_fields.append("project")

        if fields:
            needed_fields.extend(fields)

        # Do a Shotgun query if any field is missing
        missing = [needed for needed in needed_fields if needed not in shotgun_entity]
        if missing:
            consolidated = self.bridge.shotgun.find_one(
                shotgun_entity["type"],
                [["id", "is", shotgun_entity["id"]]],
                missing + shotgun_entity.keys(),
            )
            if not consolidated:
                self._logger.warning(
                    "Unable to retrieve %s %d in Shotgun." % (
                        shotgun_entity["type"],
                        shotgun_entity["id"],
                    )
                )
                return None
            shotgun_entity = consolidated

        # Ensure a consistent way to retrieve the Entity name
        if name_field != "name":
            shotgun_entity["name"] = shotgun_entity[name_field]
        return shotgun_entity

    def get_jira_value_for_shotgun_value(
        self,
        jira_project,
        jira_issue,
        jira_field,
        jira_field_schema,
        shotgun_value,
    ):
        """
        Return a Jira value corresponding to the given Shotgun value for the
        given Issue field.

        .. note:: This method only handles single values. Shotgun list values
                  must be handled by calling this method for each of the individual
                  values.

        :param jira_project: A :class:`jira.resources.Project` instance.
        :param jira_issue: A :class:`jira.resources.Issue` instance.
        :param jira_field: A Jira field id, as a string.
        :param jira_field_schema: The jira create or edit meta data for the given
                                  field.
        :param shotgun_value: A single value retrieved from Shotgun.
        :returns: A :class:`jira.resources.Resource` instance, or a dictionary,
                  or a string, depending on the field type.
        """
        # Deal with unset or empty value
        if shotgun_value is None:
            return None
        jira_type = jira_field_schema["schema"]["type"]
        if not shotgun_value:
            # Return an empty value suitable for the Jira field type
            if jira_type == "string":
                return ""
            return None

        if isinstance(shotgun_value, dict):
            # Assume a Shotgun Entity
            shotgun_value = self.consolidate_shotgun_entity(shotgun_value)

        allowed_values = jira_field_schema.get("allowedValues")
        if allowed_values:
            self._logger.debug(
                "Allowed values for %s are %s, type is %s" % (
                    jira_field,
                    allowed_values,
                    jira_field_schema.get("schema", {}).get("type"),
                )
            )
            if isinstance(shotgun_value, dict):
                sg_value_name = shotgun_value["name"]
            else:
                sg_value_name = shotgun_value
            sg_value_name = sg_value_name.lower()
            for allowed_value in allowed_values:
                # TODO: check this code actually works. For our basic implementation
                # we don't update fields with allowedValues restriction.
                if isinstance(allowed_value, dict): # Some kind of Jira Resource
                    # Jira can store the "value" with a "value" key, or a "name" key
                    if "value" in allowed_value and allowed_value["value"].lower() == sg_value_name:
                        return allowed_value
                    if "name" in allowed_value and allowed_value["name"].lower() == sg_value_name:
                        return allowed_value
                else: # Assume a string
                    if allowed_value.lower() == sg_value_name:
                        return allowed_value
            self._logger.warning(
                "Shotgun value '%s' for Jira field %s is not in the list of "
                "allowed values: %s." % (
                    shotgun_value,
                    jira_field,
                    allowed_values
                )
            )
            return None
        else:
            # In most simple cases the Jira value is the Shotgun value.
            jira_value = shotgun_value

            # Special cases
            if jira_field == "assignee":
                if isinstance(shotgun_value, dict):
                    email_address = shotgun_value.get("email")
                    if not email_address:
                        self._logger.warning(
                            "Unable to update Jira %s field from Shotgun value '%s'. "
                            "An email address is required." % (
                                jira_field,
                                shotgun_value,
                            )
                        )
                        return None
                else:
                    email_address = shotgun_value
                jira_value = self.find_jira_assignee_for_issue(
                    email_address,
                    jira_project,
                    jira_issue,
                )
            elif jira_field == "labels":
                if isinstance(shotgun_value, dict):
                    jira_value = shotgun_value["name"]
                else:
                    jira_value = shotgun_value
            elif jira_field == "summary":
                # JIRA raises an error if there are new line characters in the
                # summary for an Issue.
                jira_value = shotgun_value.replace("\n", "").replace("\r", "")
            elif jira_field == "timetracking":
                # Note: time tracking needs to be enabled in Jira
                # https://confluence.atlassian.com/adminjiracloud/configuring-time-tracking-818578858.html
                # And it does not seem that this available with new default
                # Kanban board...
                jira_value = {"originalEstimate": "%d m" % shotgun_value}

        return jira_value

    def get_jira_issue_field_sync_value(
        self,
        jira_project,
        jira_issue,
        shotgun_entity_type,
        shotgun_field,
        shotgun_event_meta
    ):
        """
        Retrieve the Jira Issue field and the value to set from the given Shotgun
        field name and its value for the given Shotgun Entity type.

        :param jira_project: A :class:`jira.resources.Project` instance.
        :param jira_issue: A :class:`jira.resources.Issue` instance.
        :param shotgun_entity_type: A Shotgun Entity type as a string.
        :param shotgun_field: A Shotgun Entity field name as a string.
        :param shotgun_event_meta: A Shotgun event meta data as a dictionary.

        :returns: A tuple with a Jira field id and a Jira value usable for an
                  update. The returned field id is `None` if no valid field or
                  value could be retrieved.
        :raises: UnsuitableShotgunValue if the Shotgun value can't be translated
                 into a valid Jira value.
        """
        field_schema = self.bridge.get_shotgun_field_schema(
            shotgun_entity_type,
            shotgun_field
        )
        if not field_schema:
            raise ValueError("Unknown Shotgun %s %s field" % (
                shotgun_entity_type, shotgun_field,
            ))
        # Retrieve the matching Jira field
        jira_field = self.get_jira_issue_field_for_shotgun_field(
            shotgun_entity_type,
            shotgun_field
        )
        # Bail out if we couldn't find a target Jira field
        if not jira_field:
            self._logger.debug(
                "Don't know how to sync Shotgun %s %s field to Jira" % (
                    shotgun_entity_type,
                    shotgun_field
                )
            )
            return None, None

        # Retrieve edit meta data for the issue
        jira_fields = self.get_jira_issue_edit_meta(jira_issue)

        # Bail out if the target Jira field is not editable
        if jira_field not in jira_fields:
            self._logger.debug(
                "Target Jira %s %s field for Shotgun %s %s field is not editable" % (
                    jira_issue.fields.issuetype,
                    jira_field,
                    shotgun_entity_type,
                    shotgun_field
                )
            )
            return None, None

        is_array = False
        jira_value = None
        # Option fields with multi-selection are flagged as array
        if jira_fields[jira_field]["schema"]["type"] == "array":
            is_array = True
            jira_value = []
        if "added" in shotgun_event_meta or "removed" in shotgun_event_meta:
            self._logger.debug(
                "Dealing with list changes added %s" % (
                    shotgun_event_meta,
                )
            )
            jira_value = self.get_jira_value_for_shotgun_list_changes(
                jira_project,
                jira_issue,
                jira_field,
                jira_fields[jira_field],
                shotgun_event_meta.get("added", []),
                shotgun_event_meta.get("removed", []),
            )
            # jira Resource instances are not json serializable so we need
            # to return their raw value
            if is_array:
                raw_values = []
                for value in jira_value:
                    if isinstance(value, jira.resources.Resource):
                        raw_values.append(value.raw)
                    else:
                        raw_values.append(value)
                jira_value = raw_values
            elif isinstance(jira_value, jira.resources.Resource):
                jira_value = jira_value.raw
        else:
            shotgun_value = shotgun_event_meta["new_value"]
            jira_value = self.get_jira_value_for_shotgun_value(
                jira_project,
                jira_issue,
                jira_field,
                jira_fields[jira_field],
                shotgun_value,
            )
            if jira_value is None and shotgun_value:
                # Couldn't get a Jira value, cancel update
                raise UnsuitableShotgunValue(
                    jira_field,
                    shotgun_value,
                    "Couldn't translate Shotgun value %s to a valid value "
                    "for Jira field %s" % (
                        shotgun_value,
                        jira_field,
                    )
                )
            if isinstance(jira_value, jira.resources.Resource):
                # jira.Resource instances are not json serializable so we need
                # to return their raw value
                jira_value = jira_value.raw
            if is_array:
                # Single Shotgun value mapped to Jira list value
                jira_value = [jira_value] if jira_value else []

        try:
            jira_value = self.sanitize_jira_update_value(
                jira_value, jira_fields[jira_field]
            )
        except UserWarning as e:
            self._logger.warning(e)
            # Cancel update
            return None, None
        return jira_field, jira_value

    def get_shotgun_entity_field_sync_value(self, shotgun_entity, jira_issue, jira_field_id, change):
        """
        Retrieve the Shotgun Entity field and the value to set from the given Jira
        Issue field value.

        :param shotgun_entity: A Shotgun Entity dictionary with at least a type
                               and an id.
        :param jira_issue: A Jira Issue raw dictionary.
        :param jira_field_id: A Jira field id as a string.
        :param change: A dictionary with the field change retrieved from the
                       event change log.
        :returns: A tuple with a Jira field id and a Jira value usable for an
                  update. The returned field id is `None` if no valid field or
                  value could be retrieved.
        :raises: UnsuitableJiraValue if the Jira value can't be translated
                 into a valid Shotgun value.
        :raises: ValueError if the target Shotgun field is not valid.
        """

        # Retrieve the Shotgun field to update
        shotgun_field = self.get_shotgun_entity_field_for_issue_field(
            "Issue",
            jira_field_id,
        )
        if not shotgun_field:
            self._logger.debug(
                "Don't know how to sync Jira field %s to Shotgun." % jira_field_id
            )
            return None, None

        # TODO: handle Shotgun Project specific fields?
        shotgun_field_schema = self.bridge.get_shotgun_field_schema(
            shotgun_entity["type"],
            shotgun_field
        )
        if not shotgun_field_schema:
            raise ValueError("Unknown Shotgun %s %s field" % (
                shotgun_entity["type"], shotgun_field,
            ))

        if not shotgun_field_schema["editable"]["value"]:
            self._logger.debug("Shotgun field %s.%s is not editable" % (
                shotgun_entity["type"], shotgun_field,
            ))
            return None, None

        # Special cases
        if jira_field_id == "assignee":
            shotgun_value = self.get_shotgun_assignment_from_jira_issue_change(
                shotgun_entity,
                shotgun_field,
                shotgun_field_schema,
                jira_issue,
                change
            )
            return shotgun_field, shotgun_value
        # General case
        shotgun_value = self.get_shotgun_value_from_jira_issue_change(
            shotgun_entity,
            shotgun_field,
            shotgun_field_schema,
            change
        )
        return shotgun_field, shotgun_value

    def get_shotgun_assignment_from_jira_issue_change(
        self,
        shotgun_entity,
        shotgun_field,
        shotgun_field_schema,
        jira_issue,
        change,
    ):
        """
        Retrieve a Shotgun assignmemnt value from the given Jira change.

        This method supports single entity and multi entity fields.

        :param str shotgun_entity: A Shotgun Entity dictionary as retrieved from
                                   Shotgun.
        :param str shotgun_field: The Shotgun Entity field to get a value for.
        :param shotgun_field_schema: The Shotgun Entity field schema.
        :param jira_issue: A Jira Issue raw dictionary.
        :param change: A Jira event changelog dictionary with 'from' and
                       'to' keys.

        :returns: The updated value to set in Shotgun for the given field.
        :raises: ValueError if the target Shotgun field is not suitable
        """
        # Change log example
        # {
        # u'from': u'ford.prefect1',
        # u'to': None,
        # u'fromString': u'Ford Prefect',
        # u'field': u'assignee',
        # u'toString': None,
        # u'fieldtype': u'jira',
        # u'fieldId': u'assignee'
        # }

        data_type = shotgun_field_schema["data_type"]["value"]
        if data_type not in ["multi_entity", "entity"]:
            raise ValueError(
                "Don't know how to handle %s field type for Shotgun %s.%s assignements" % (
                    data_type,
                    shotgun_entity["type"],
                    shotgun_field
                )
            )

        sg_valid_types = shotgun_field_schema["properties"]["valid_types"]["value"]
        if "HumanUser" not in sg_valid_types:
            raise ValueError(
                "Shotgun %s.%s assignemnt field does not accept HumanUser but %s" % (
                    shotgun_entity["type"],
                    shotgun_field,
                    sg_valid_types
                )
            )
        current_sg_assignment = shotgun_entity.get(shotgun_field)
        from_assignee = change["from"]
        to_assignee = change["to"]
        if data_type == "multi_entity":
            if from_assignee:
                # Try to remove the old assignee from the Shotgun assignment
                jira_user = self.jira.user(from_assignee)
                sg_user = self.shotgun.find_one(
                    "HumanUser",
                    [["email", "is", jira_user.emailAddress]],
                    ["email", "name"]
                )
                if not sg_user:
                    self._logger.debug(
                        "Unable to retrieve a Shotgun user with email address %s" % (
                            jira_user.emailAddress
                        )
                    )
                else:
                    for i, current_sg in enumerate(current_sg_assignment):
                        if current_sg["type"] == sg_user["type"] and current_sg["id"] == sg_user["id"]:
                            self._logger.debug(
                                "Removing user %s from Shotgun assignment" % (
                                    sg_user
                                )
                            )
                            del current_sg_assignment[i]
                            # Note: we're assuming there is no duplicates in the
                            # list. Otherwise we would have to ensure we use an
                            # iterator allowing the list to be modified while
                            # iterating
                            break
            if to_assignee:
                # Try to add the new assignee to the Shotgun assignment
                # Use the Issue assignee value to avoid a Jira user query
                jira_user = jira_issue["fields"]["assignee"]
                sg_user = self.shotgun.find_one(
                    "HumanUser",
                    [["email", "is", jira_user["emailAddress"]]],
                    ["email", "name"]
                )
                if not sg_user:
                    raise UnsuitableJiraValue(
                        "Unable to retrieve a Shotgun user with email address %s" % (
                            jira_user.emailAddress
                        )
                    )
                for current_sg_user in current_sg_assignment:
                    if current_sg_user["type"] == sg_user["type"] and current_sg_user["id"] == sg_user["id"]:
                        break
                else:
                    self._logger.debug(
                        "Adding user %s to Shotgun assignment %s" % (
                            sg_user, current_sg_assignment
                        )
                    )
                    current_sg_assignment.append(sg_user)
        else: # data_type == "entity":
            if from_assignee:
                # Try to remove the old assignee from the Shotgun assignment
                jira_user = self.jira.user(from_assignee)
                sg_user = self.shotgun.find_one(
                    "HumanUser",
                    [["email", "is", jira_user.emailAddress]],
                    ["email", "name"]
                )
                if not sg_user:
                    self._logger.debug(
                        "Unable to retrieve a Shotgun user with email address %s" % (
                            jira_user.emailAddress
                        )
                    )
                else:
                    if current_sg_assignment["type"] == sg_user["type"] and current_sg_assignment["id"] == sg_user["id"]:
                        self._logger.debug(
                            "Removing user %s from Shotgun assignment" % (
                                sg_user
                            )
                        )
                        current_sg_assignment = None

            if to_assignee and not current_sg_assignment:
                # Try to set the new assignee to the Shotgun assignment
                # Use the Issue assignee value to avoid a Jira user query
                # Note that we are dealing here with a Jira raw value dict, not
                # a jira.resources.Resource instance.
                jira_user = jira_issue["fields"]["assignee"]
                sg_user = self.shotgun.find_one(
                    "HumanUser",
                    [["email", "is", jira_user["emailAddress"]]],
                    ["email", "name"]
                )
                if not sg_user:
                    raise UnsuitableJiraValue(
                        "Unable to retrieve a Shotgun user with email address %s" % (
                            jira_user.emailAddress
                        )
                    )
                current_sg_assignment = sg_user
        return current_sg_assignment

    def get_shotgun_value_from_jira_issue_change(
        self,
        shotgun_entity,
        shotgun_field,
        shotgun_field_schema,
        change,
    ):
        """
        Return a Shotgun value suitable to update the given Shotgun Entity field
        from the given Jira change.

        :param str shotgun_entity: A Shotgun Entity dictionary as retrieved from
                                   Shotgun.
        :param str shotgun_field: The Shotgun Entity field to get a value for.
        :param shotgun_field_schema: The Shotgun Entity field schema.
        :param change: A Jira event changelog dictionary with 'fromString' and
                       'toString' keys.
        :raises: RuntimeError if the Shotgun Entity can't be retrieved from Shotgun.
        """
        data_type = shotgun_field_schema["data_type"]["value"]
        if data_type == "text":
            return change["toString"]

        if data_type == "list":
            value = change["toString"]
            if not value:
                return ""
            # Make sure the value is available in the list of possible values
            all_allowed = shotgun_field_schema["properties"]["valid_values"]["value"]
            for allowed in all_allowed:
                if value.lower() == allowed.lower():
                    return allowed
            # The value is not allowed, update the schema to allow it. This is
            # provided as a convenience, otherwise keeping the list of allowed
            # values on both side could be very painful. An other option here
            # would be to raise an UnsuitableJiraValue
            all_allowed.append(value)
            self._logger.info(
                "Updating %s.%s schema with %s valid values" % (
                    all_allowed
                )
            )
            self.shotgun.schema_field_update(
                shotgun_entity["type"],
                shotgun_field,
                {"valid_values": all_allowed}
            )
            # Clear the schema to take into account the change we just made.
            self.bridge.clear_cached_shotgun_field_schema(shotgun_entity["type"])
            return value

        if data_type == "status_list":
            value = change["toString"]
            if not value:
                # Unset the status in Shotgun
                return None
            # Look up a matching Shotgun status from our mapping
            # Please note that if we have multiple matching values the first
            # one will be arbitrarily returned.
            for sg_code, jira_name in self.sg_jira_statuses_mapping.iteritems():
                if value.lower() == jira_name.lower():
                    return sg_code
            # No match.
            raise UnsuitableJiraValue(
                "Unable to find a matching Shotgun status for %s from %s" % (
                    value,
                    self.sg_jira_statuses_mapping
                )
            )

        if data_type == "multi_entity":
            # If the Jira field is an array we will get the list of resource
            # names in a string, separated by spaces.
            # We're assuming here that if someone maps a Jira simple field to
            # a Shotgun multi entity field the same convention will be applied
            # and spaces will be used as separators.
            allowed_entities = shotgun_field_schema["properties"]["valid_types"]["value"]
            old_list = set()
            new_list = set()
            if change["fromString"]:
                old_list = set(change["fromString"].split(" "))
            if change["toString"]:
                new_list = set(change["toString"].split(" "))
            removed_list = old_list - new_list
            added_list = new_list - old_list
            # Make sure we have the current value and the Shotgun project
            consolidated = self.consolidate_shotgun_entity(
                shotgun_entity,
                fields=[shotgun_field, "project"]
            )
            if not consolidated:
                raise RuntimeError(
                    "Unable to retrieve the %s with the id %d from Shotgun" % (
                        shotgun_entity["type"],
                        shotgun_entity["id"]
                    )
                )
            current_sg_value = consolidated[shotgun_field]
            for removed in removed_list:
                # Try to remove the entries from the Shotgun value. We make a
                # copy of the list so we can delete entries while iterating
                for i, sg_value in enumerate(list(current_sg_value)):
                    # Match the SG entity name, because this is retrieved
                    # from the entity holding the list, we do have a "name" key
                    # even if the linked Entities use another field to store their
                    # name e.g. "code"
                    if removed.lower() == sg_value["name"].lower():
                        self._logger.debug(
                            "Removing %s for %s from Shotgun value %s" % (
                                sg_value, removed, current_sg_value,
                            )
                        )
                        del current_sg_value[i]
            for added in added_list:
                # Check if the value is already there
                self._logger.debug("Checking %s against %s" % (
                    added, current_sg_value,
                ))
                for sg_value in current_sg_value:
                    # Match the SG entity name, because this is retrieved
                    # from the entity holding the list, we do have a "name" key
                    # even if the linked Entities use another field to store their
                    # name e.g. "code"
                    if added.lower() == sg_value["name"].lower():
                        self._logger.debug(
                            "%s is already in current value as %s" % (
                                added, sg_value,
                            )
                        )
                        break
                else:
                    # We need to retrieve a matching Entity from Shotgun and
                    # add it to the list, if we found one.
                    sg_value = self.match_shotgun_entity_by_name(
                        added,
                        allowed_entities,
                        consolidated["project"]
                    )
                    if sg_value:
                        self._logger.debug(
                            "Adding %s for %s to Shotgun value %s" % (
                                sg_value, added, current_sg_value,
                            )
                        )
                        current_sg_value.append(sg_value)
                    else:
                        self._logger.debug(
                            "Couldn't retrieve a %s named '%s'" % (
                                " or a ".join(allowed_entities),
                                added
                            )
                        )

            return current_sg_value
        raise ValueError("%s Change %s" % (data_type, change))

        if data_type == "entity":
            pass

    def match_shotgun_entity_by_name(self, name, entity_types, shotgun_project):
        """
        Retrieve a Shotgun Entity with the given name from the given list of
        Entity types.

        Project Shotgun Entities are restricted to the given Shotgun Project.

        :param str name: A name to match.
        :param entity_types: A list of Shotgun Entity types to consider.
        :param shotgun_project: A Shotgun Project dictionary.
        :return: A Shotgun Entity dictionary or `None`.
        """
        for entity_type in entity_types:
            name_field = self.bridge.get_sg_entity_name_field(
                entity_type
            )
            filter = [[name_field, "is", name]]
            fields = [name_field]
            if self.is_project_shotgun_entity(entity_type):
                filter.append(
                    ["project", "is", shotgun_project]
                )
                fields.append("project")
            sg_value = self.shotgun.find_one(
                entity_type,
                filter,
                fields,
            )
            if sg_value:
                return self.consolidate_shotgun_entity(sg_value)
        return None

    def sanitize_jira_update_value(self, jira_value, jira_field_schema):
        """
        Perform sanity checks for the given Jira value and ensure it can be used
        to update the Jira field with the given schema.

        :returns: A Jira value which can safely be used to update the Jira field.
        :raises: UserWarning if a safe value can't be obtained.
        """
        # If the value is empty but required, check if Jira will be able to use
        # a default value. Default values are only available when creating Issues
        if not jira_value and jira_field_schema["required"]:
            # Create meta data has a "hasDefaultValue" property, edit meta data
            # does not have this property.
            has_default = jira_field_schema.get("hasDefaultValue")
            if not has_default:
                raise UserWarning(
                    "Invalid value %s: Field %s requires a value and does not "
                    "provide a default value" % (
                        jira_value,
                        jira_field_schema["name"]
                    )
                )
        # Jira doesn't allow single-line text entry fields to be longer than
        # 255 characters, so we truncate the string data and add a little
        # message -- so users know to look at Shotgun. Note that this
        # "feature" could result in data loss; if the truncated text is
        # subsequently modified in Jira, the truncated result will be sent
        # to Shotgun by the Jira sync webhook.
        if jira_field_schema["schema"]["type"] == "string" and isinstance(jira_value, str):
            # Reference:
            # com.atlassian.jira.plugin.system.customfieldtypes:textfield
            # com.atlassian.jira.plugin.system.customfieldtypes:textarea
            if jira_field_schema["schema"].get("custom") == "com.atlassian.jira.plugin.system.customfieldtypes:textfield":
                if len(jira_value) > 255:
                    self._logger.warning(
                        "String data is too long (> 255 chars). Truncating for display in Jira."
                    )
                    message = "... [see Shotgun]."
                    jira_value = jira_value[:(255 - len(message))] + message

        self._logger.debug(
            "Sanitized value for %s is %s" % (
                jira_field_schema["name"],
                jira_value,
            )
        )
        return jira_value

    def find_jira_assignee_for_issue(self, user_email, jira_project=None, jira_issue=None):
        """
        Return a Jira user the given issue can be assigned to, based
        on the given email address.

        A Jira Project must be specified when creating an Issue. A Jira Issue must
        be specified when editing an Issue.

        :param jira_project: A :class:`jira.resources.Project` instance or None.
        :param jira_issue: A :class:`jira.resources.Issue` instance or None.
        :param user_email: An email address as a string.
        :returns: A :class:`jira.resources.User` instance or None.
        :raises: ValueError if no Project nor Issue is specified.
        """
        return self.find_jira_user(
            user_email,
            jira_project,
            jira_issue,
            for_assignment=True
        )

    def _search_allowed_users_for_issue(self, user, project, issueKey, startAt=0, maxResults=50):
        """
        Wrapper around jira.search_allowed_users_for_issue to make its parameter
        consistent with jira.search_assignable_users_for_issues parameters.
        """
        # Note: this does not work and requires a user name or email to be specified.
        # There are some various discussions about it, mentionning that using
        # "." or "%" or "_" could act as a wildcard but none of them worked.
        return self.jira.search_allowed_users_for_issue(
            user if user else ".",
            projectKey=project.key if project else None,
            issueKey=issueKey,
            startAt=startAt,
            maxResults=maxResults
        )
        # An attempt to use a query param instead of the username param, which is
        # being deprecated, used by the method above. This didn't work better ...
        # https://developer.atlassian.com/cloud/jira/platform/rest/v2?_ga=2.239994883.1204798848.1547548670-1513186087.1542632955#api-api-2-user-search-query-key-get
#        params = {
#            "query": user or "_"
#        }
#        if issueKey is not None:
#            params["issueKey"] = issueKey
#        if project is not None:
#            params["projectKey"] = project.key
#        return self.jira._fetch_pages(
#            jira.resources.User,
#            None,
#            "user/viewissue/search",
#            startAt,
#            maxResults,
#            params
#        )

    def find_jira_user(self, user_email, jira_project=None, jira_issue=None, for_assignment=False):
        """
        Return a Jira an assignable user or with browse permission for the given
        Project or Issue, with the given email address.

        .. note:: Due to problems with user searching in Jira, this method always
                  returns assignable users for the time being.

        :param jira_project: A :class:`jira.resources.Project` instance or None.
        :param jira_issue: A :class:`jira.resources.Issue` instance or None.
        :param user_email: An email address as a string.
        :param for_assignment: A boolean, if `False` the user just needs to have read
                            permission. If `True` the user needs to be suitable for
                            Issue assignments.
        :returns: A :class:`jira.resources.User` instance or None.
        :raises: ValueError if no Project nor Issue is specified.
        """

        if not jira_project and not jira_issue:
            raise ValueError(
                "Either a Jira Project or a Jira Issue must be specified"
            )

        if not user_email:
            return None

        if for_assignment:
            search_method = self.jira.search_assignable_users_for_issues
        else:
            # See comments in _search_allowed_users_for_issue: searching for users
            # does not seem to work very well, so, for the time being, we use the
            # only method that can be trusted and only consider assignable users.
            # search_method = self._search_allowed_users_for_issue
            search_method = self.jira.search_assignable_users_for_issues

        # Note: There is a Jira bug that prevents searching by email address from working on
        # some instances. In this case, we fall back on paging through ALL results to
        # ensure don't incorrectly miss matching the user.
        # See: https://jira.atlassian.com/browse/JRASERVER-61772
        # See: https://jira.atlassian.com/browse/JRACLOUD-61772

        jira_assignee = None

        # Direct user search with their email
        self._logger.debug("Looking up %s in assignable users" % user_email)
        jira_users = search_method(
            user_email,
            project=jira_project,
            issueKey=jira_issue.key if jira_issue else None,
            maxResults=2000,
        )
        if jira_users:
            jira_assignee = jira_users[0]
            if len(jira_users) > 1:
                self._logger.warning(
                    "Found multiple assignable Jira users with email address %s. "
                    "Using the first one: %s" % (
                        user_email,
                        jira_users
                    )
                )
            self._logger.debug("Found Jira Assignee %s" % jira_assignee)
            return jira_assignee

        # Because of the bug mentioned above, fall back on matching users ourself.
        self._logger.debug(
            "No assignable users found matching %s. Searching all assignable users "
            "manually" % user_email
        )
        uemail = user_email.lower()
        start_idx = 0
        self._logger.debug("Querying assignable users starting at #%d" % start_idx)
        jira_users = search_method(
            None,
            project=jira_project,
            issueKey=jira_issue.key if jira_issue else None,
            maxResults=2000,
            startAt=start_idx,
        )
        while jira_users:
            for jira_user in jira_users:
                if jira_user.emailAddress and jira_user.emailAddress.lower() == uemail:
                    jira_assignee = jira_user
                    break
            if jira_assignee:
                break
            else:
                start_idx += len(jira_users)
                self._logger.debug(
                    "Querying assignable users starting at #%d" % start_idx
                )
                jira_users = search_method(
                    None,
                    project=jira_project,
                    issueKey=jira_issue.key if jira_issue else None,
                    maxResults=2000,
                    startAt=start_idx,
                )
                self._logger.debug("Found %s users" % (len(jira_users)))

        if not jira_assignee:
            if jira_issue:
                self._logger.warning(
                    "Unable to retrieve a Jira user with email %s for Issue %s" % (
                        user_email,
                        jira_issue,
                    )
                )
            else:
                self._logger.warning(
                    "Unable to retrieve a Jira user with email %s for Project %s" % (
                        user_email,
                        jira_project,
                    )
                )

        self._logger.debug("Found Jira Assignee %s" % jira_assignee)
        return jira_assignee

    def sync_shotgun_status_to_jira(self, jira_issue, shotgun_status, comment):
        """
        Set the status of the Jira Issue based on the given Shotgun status.

        :param jira_issue: A :class:`jira.resources.Issue` instance.
        :param shotgun_status: A Shotgun status short code as a string.
        :param comment: A string, a comment to apply to the Jira transition.
        :returns: `True` if the status was successfully set, `False` otherwise.
        """
        jira_status = self.sg_jira_statuses_mapping.get(shotgun_status)
        if not jira_status:
            self._logger.warning(
                "Unable to retrieve corresponding Jira status for %s" % shotgun_status
            )
            return False

        if jira_issue.fields.status.name == jira_status:
            self._logger.debug("Jira issue %s is already '%s'" % (
                jira_issue, jira_status
            ))
            return True

        # Retrieve available transitions for the issue including fields on the
        # transition screen.
        jira_transitions = self.jira.transitions(
            jira_issue,
            expand="transitions.fields"
        )
        for tra in jira_transitions:
            # Match a transition with the expected status name
            if tra["to"]["name"] == jira_status:
                self._logger.info(
                    "Found transition to %s for %s: %s" % (
                        jira_status,
                        jira_issue,
                        tra,
                    )
                )
                # Iterate over any fields for transition and find required fields
                # that don't have a default value. Set the value using our defaults.
                # NOTE: This only supports text fields right now.
                fields = {}
                if "fields" in tra:
                    for field_name, details in tra["fields"].iteritems():
                        # If field is required, it doesn't currently have a value and
                        # there is no default value provided by Jira, use our hardcoded
                        # default value.
                        # Eventually, this should be moved to a flexible framework for clients
                        # to customize on their own like Hooks.
                        # Note: This is not reliable. The "fields" key we get back from the
                        # transitions call above only includes fields on the transition screen
                        # and each field's "required" key refers to whether the field is
                        # globally set as required. However, you can set a validator
                        # on the transition that requires a globally optional field be non-empty.
                        # The field will still show up as "required=False" since the field isn't
                        # configured as a globally required field.
                        if details["required"] and (
                            not getattr(jira_issue.fields, field_name)
                            and not details.get("hasDefaultValue")
                        ):
                            # The resolution field is often required in transitions. We don't
                            # currently support configuring this so we use the first
                            # allowed value.
                            if details["schema"]["type"] == "resolution":
                                fields[field_name] = details["allowedValues"][0]
                                self._logger.info(
                                    "Setting resolution to first allowedValue: %s" %
                                    details["allowedValues"][0]
                                )
                            # Text fields are just filled with our default value to satisfy
                            # the requirement.
                            elif details["schema"]["type"] == "text":
                                fields[field_name] = comment

                # We add a comment by default in case it is required by the transition validator.
                # Note that the comment will only be saved if it is visible on a transition
                # screen.
                params = {
                    "comment": comment,
                }
                # If there are any required text fields we have
                # provided values for, then add the "fields" param. When "fields" is specified,
                # all other keyword params are ignored (including the comment param setup above).
                if fields:
                    params["fields"] = fields

                self._logger.info("Transitioning Issue %s to %s. Params: %s" % (
                    jira_issue,
                    tra["name"],
                    params
                ))
                self.jira.transition_issue(
                    jira_issue,
                    tra["id"],
                    **params
                )
                return True

        self._logger.warning(
            "Couldn't find any Jira transition with %s as target" % jira_status
        )
        self._logger.debug("Available transitions are %s" % jira_transitions)
        return False

    def sync_shotgun_cced_changes_to_jira(self, jira_issue, added, removed):
        """
        Update the given Jira Issue watchers from the given Shotgun changes.

        :param jira_issue: A :class:`jira.resources.Issue` instance.
        :param added: A list of Shotgun user dictionaries.
        :param removed: A list of Shotgun user dictionaries.
        """

        for user in removed:
            if user["type"] != "HumanUser":
                # Can be a Group, a ScriptUser
                continue
            sg_user = self.consolidate_shotgun_entity(user)
            if sg_user:
                jira_user = self.find_jira_user(
                    sg_user["email"],
                    jira_issue=jira_issue,
                )
                if jira_user:
                    # No need to check if the user is in the current watchers list:
                    # Jira handles that gracefully.
                    self.jira.remove_watcher(jira_issue, jira_user.name)

        for user in added:
            if user["type"] != "HumanUser":
                # Can be a Group, a ScriptUser
                continue
            sg_user = self.consolidate_shotgun_entity(user)
            if sg_user:
                jira_user = self.find_jira_user(
                    sg_user["email"],
                    jira_issue=jira_issue,
                )
                if jira_user:
                    self.jira.add_watcher(jira_issue, jira_user.name)

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :returns: True if the event is accepted for processing, False otherwise.
        """

        # We require a non empty event.
        if not event:
            return False

        # Check we have a Project
        if not event.get("project"):
            self._logger.debug("Rejecting event %s with no project." % event)
            return False

        # Check the event meta data
        meta = event.get("meta")
        if not meta:
            self._logger.debug("Rejecting event %s with no meta data." % event)
            return False
        if meta.get("type") != "attribute_change":
            self._logger.debug("Rejecting event %s with wrong or missing type." % event)
            return False
        field = meta.get("attribute_name")
        if field not in self.supported_shotgun_fields(entity_type):
            self._logger.debug(
                "Rejecting event %s with unsupported or missing field %s." % (
                    event, field
                )
            )
            return False

        # Check we didn't trigger the event to avoid infinite loops.
        user = event.get("user")
        current_user = self._bridge.current_shotgun_user
        if user and current_user:
            if user["type"] == current_user["type"] and user["id"] == current_user["id"]:
                self._logger.debug("Rejecting event %s created by us." % event)
                return False

        return True

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Shotgun event for the given Shotgun Entity

        Must be re-implemented in deriving classes.

        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event meta data for the change.
        """
        raise NotImplementedError

    def accept_jira_event(self, resource_type, resource_id, event):
        """
        Accept or reject the given event for the given Jira resource.

        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event is accepted for processing, False otherwise.
        """
        # Check we didn't trigger the event to avoid infinite loops.
        user = event.get("user")
        if user:
            if user["name"].lower() == self.bridge.current_jira_username.lower():
                self._logger.debug("Rejecting event %s triggered by us (%s)" % (
                    event,
                    user["name"],
                ))
                return False
            if user["emailAddress"].lower() == self.bridge.current_jira_username.lower():
                self._logger.debug("Rejecting event %s triggered by us (%s)" % (
                    event,
                    user["emailAddress"],
                ))
                return False
        return True

    def process_jira_event(self, resource_type, resource_id, event):
        """
        Process the given Jira event for the given Jira resource.

        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        """
        self._logger.info("Syncing in SG %s(%s) for event %s" % (
            resource_type,
            resource_id,
            event
        ))

    def is_project_shotgun_entity(self, entity_type):
        """
        Return `True` if the given Shotgun Entity type is a project Entity,
        `False` if it is a non-project Entity.

        :param str entity_type: A Shotgun Entity type.
        """
        return self.bridge.is_project_shotgun_entity(entity_type)
