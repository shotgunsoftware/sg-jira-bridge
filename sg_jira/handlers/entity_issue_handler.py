# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import jira

from ..errors import InvalidShotgunValue, InvalidJiraValue
from .sync_handler import SyncHandler


class EntityIssueHandler(SyncHandler):
    """
    Base class for handlers syncing a Shotgun Entity to a Jira Issue.
    """

    def __init__(self, syncer, issue_type):
        """
        Instantiate an Entity Issue handler for the given syncer.

        :param syncer: A :class:`Syncer` instance.
        :param str issue_type: A target Issue type, e.g. 'Task', 'Story'.
        """
        super(EntityIssueHandler, self).__init__(syncer)
        self._issue_type = issue_type

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
            self._logger.debug("Rejecting event %s without a %s issue type" % (event, self._issue_type))
            return False

        shotgun_id = fields.get(self._jira.jira_shotgun_id_field)
        shotgun_type = fields.get(self._jira.jira_shotgun_type_field)
        if not shotgun_id or not shotgun_type:
            self._logger.debug(
                "Rejecting event %s for %s %s not linked to a Shotgun Entity" % (
                    event,
                    issue_type["name"],
                    resource_id,
                )
            )
            return False

        return True

    def _create_jira_issue_for_entity(
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

        # Retrieve the reporter, either the user who created the Entity or the
        # Jira user used to run the syncing.
        reporter_name = self._jira.current_user()
        created_by = sg_entity["created_by"]
        if created_by["type"] == "HumanUser":
            user = self._shotgun.consolidate_entity(created_by)
            if user:
                user_email = user["email"]
                jira_user = self._jira.find_jira_user(
                    user_email,
                    jira_project=jira_project,
                )
                # If we found a Jira user, use his name as the reporter name,
                # otherwise use the reporter name retrieved from the user used
                # to run the bridge.
                if jira_user:
                    reporter_name = jira_user.name
        else:
            self._logger.debug(
                "Ignoring created by %s which is not a HumanUser." % created_by
            )

        shotgun_url = self._shotgun.get_entity_page_url(sg_entity)

        # Note that JIRA raises an error if there are new line characters in the
        # summary for an Issue or if the description field is not set.
        if description is None:
            description = ""
        data = {
            "project": jira_project.raw,
            "summary": summary.replace("\n", "").replace("\r", ""),
            "description": description,
            self._jira.jira_shotgun_id_field: "%d" % sg_entity["id"],
            self._jira.jira_shotgun_type_field: sg_entity["type"],
            self._jira.jira_shotgun_url_field: shotgun_url,
            "reporter": {"name": reporter_name},
        }
        if properties:
            data.update(properties)

        self._logger.info("Creating Jira issue for %s with %s" % (
            sg_entity, data
        ))

        return self._jira.create_issue_from_data(
            jira_project,
            issue_type,
            data,
        )

    def _get_jira_issue_field_sync_value(
        self,
        jira_project,
        jira_issue,
        shotgun_entity_type,
        shotgun_field,
        added=None,
        removed=None,
        new_value=None,
    ):
        """
        Retrieve the Jira Issue field and the value to set from the given Shotgun
        field name and its value for the given Shotgun Entity type.

        :param jira_project: A :class:`jira.resources.Project` instance.
        :param jira_issue: A :class:`jira.resources.Issue` instance.
        :param shotgun_entity_type: A Shotgun Entity type as a string.
        :param shotgun_field: A Shotgun Entity field name as a string.
        :param added:
        :param removed:
        :param new_value:

        :returns: A tuple with a Jira field id and a Jira value usable for an
                  update. The returned field id is `None` if no valid field or
                  value could be retrieved.
        :raises: InvalidShotgunValue if the Shotgun value can't be translated
                 into a valid Jira value.
        """
        # Retrieve the matching Jira field
        jira_field = self._get_jira_issue_field_for_shotgun_field(
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
        jira_fields = self._jira.get_jira_issue_edit_meta(jira_issue)

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

        if added is not None or removed is not None:
            self._logger.debug(
                "Dealing with list changes added %s, removed %s" % (
                    added,
                    removed
                )
            )
            jira_value = self._get_jira_value_for_shotgun_list_changes(
                jira_project,
                jira_issue,
                jira_field,
                jira_fields[jira_field],
                added or [],
                removed or [],
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
            shotgun_value = new_value
            jira_value = self._get_jira_value_for_shotgun_value(
                jira_project,
                jira_issue,
                jira_field,
                jira_fields[jira_field],
                shotgun_value,
            )
            if jira_value is None and shotgun_value:
                # Couldn't get a Jira value, cancel update
                raise InvalidShotgunValue(
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
            jira_value = self._jira.sanitize_jira_update_value(
                jira_value, jira_fields[jira_field]
            )
        except UserWarning as e:
            self._logger.warning(e)
            # Cancel update
            return None, None
        return jira_field, jira_value

    def _get_jira_issue_field_for_shotgun_field(self, shotgun_entity_type, shotgun_field):
        """
        Needs to be re-implemented in deriving classes and return the Jira Issue
        field id to use to sync the given Shotgun Entity type field.

        :returns: A string or `None`.
        """
        raise NotImplementedError

    def _get_jira_value_for_shotgun_list_changes(
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
                    value = self._get_jira_value_for_shotgun_value(
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
                value = self._get_jira_value_for_shotgun_value(
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
                    value = self._get_jira_value_for_shotgun_value(
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
                    value = self._get_jira_value_for_shotgun_value(
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

    def _get_jira_value_for_shotgun_value(
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
#        if shotgun_value is None:
#            return None
        self._logger.debug("Getting Jira value for Shotgun value %s" % shotgun_value)
        jira_type = jira_field_schema["schema"]["type"]
        if not shotgun_value:
            # Return an empty value suitable for the Jira field type
            if jira_type == "string":
                return ""
            if jira_type == "timetracking":
                return {"originalEstimate": "0 m"}

            self._logger.debug(
                "Returning `None` for Jira %s field type" % jira_type
            )
            return None

        if isinstance(shotgun_value, dict):
            # Assume a Shotgun Entity
            shotgun_value = self._shotgun.consolidate_entity(shotgun_value)

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
                if isinstance(allowed_value, dict):  # Some kind of Jira Resource
                    # Jira can store the "value" with a "value" key, or a "name" key
                    if "value" in allowed_value and allowed_value["value"].lower() == sg_value_name:
                        return allowed_value
                    if "name" in allowed_value and allowed_value["name"].lower() == sg_value_name:
                        return allowed_value
                else:  # Assume a string
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
            self._logger.debug("Special cases for %s: %s" % (jira_field, jira_value))
            # Special cases
            if jira_field in ["assignee", "reporter"]:
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
                jira_value = self._jira.find_jira_assignee_for_issue(
                    email_address,
                    jira_project,
                    jira_issue,
                )
            elif jira_field == "labels":
                if isinstance(shotgun_value, dict):
                    jira_value = shotgun_value["name"]
                else:
                    jira_value = shotgun_value
                # Jira does not accept spaces in labels.
                # Note: we could try to sanitize the data with "_" but then we
                # could end up having conflicts when syncing back the sanitized
                # value from Jira. Seems safer to just not sync it.
                if " " in jira_value:
                    raise InvalidShotgunValue(
                        jira_field,
                        shotgun_value,
                        "Jira labels can't contain spaces"
                    )
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

    def _sync_shotgun_status_to_jira(self, jira_issue, shotgun_status, comment):
        """
        Set the status of the Jira Issue based on the given Shotgun status.

        :param jira_issue: A :class:`jira.resources.Issue` instance.
        :param shotgun_status: A Shotgun status short code as a string.
        :param comment: A string, a comment to apply to the Jira transition.
        :returns: `True` if the status was successfully set, `False` otherwise.
        """
        jira_status = self._sg_jira_statuses_mapping.get(shotgun_status)
        if not jira_status:
            self._logger.warning(
                "Unable to retrieve corresponding Jira status for %s" % shotgun_status
            )
            return False

        return self._jira.set_jira_issue_status(jira_issue, jira_status, comment)

    def _sync_shotgun_cced_changes_to_jira(self, jira_issue, added, removed):
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
            sg_user = self._shotgun.consolidate_entity(user)
            if sg_user:
                jira_user = self._jira.find_jira_user(
                    sg_user["email"],
                    jira_issue=jira_issue,
                )
                if jira_user:
                    # No need to check if the user is in the current watchers list:
                    # Jira handles that gracefully.
                    self._logger.debug(
                        "Removing %s from %s watchers list." % (
                            jira_user.name,
                            jira_issue
                        )
                    )
                    self._jira.remove_watcher(jira_issue, jira_user.name)

        for user in added:
            if user["type"] != "HumanUser":
                # Can be a Group, a ScriptUser
                continue
            sg_user = self._shotgun.consolidate_entity(user)
            if sg_user:
                jira_user = self._jira.find_jira_user(
                    sg_user["email"],
                    jira_issue=jira_issue,
                )
                if jira_user:
                    self._logger.debug(
                        "Adding %s to %s watchers list." % (
                            jira_user.name,
                            jira_issue
                        )
                    )
                    self._jira.add_watcher(jira_issue, jira_user.name)

    @property
    def _supported_shotgun_fields_for_jira_event(self):
        """"
        Return the list of fields this handler can process for a Jira event.

        Needs to be re-implemented in deriving classes.

        :returns: A list of strings.
        """
        raise NotImplementedError

    def process_jira_event(self, resource_type, resource_id, event):
        """
        Process the given Jira event for the given Jira resource.

        :param str resource_type: The type of Jira resource to sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event was successfully processed, False if the
                  sync didn't happen for any reason.
        """
        jira_issue = event["issue"]
        fields = jira_issue["fields"]
        issue_type = fields["issuetype"]

        shotgun_id = fields.get(self._jira.jira_shotgun_id_field)
        if not shotgun_id.isdigit():
            raise ValueError(
                "Invalid Shotgun id %s, it should be an integer" % shotgun_id
            )
        shotgun_type = fields.get(self._jira.jira_shotgun_type_field)
        # Collect the list of fields we might need to process the event
        sg_fields = self._supported_shotgun_fields_for_jira_event
        sg_entity = self._shotgun.consolidate_entity(
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
            # in the change payload or just the field name.
            # If we don't have the field id, retrieve it from our internal mapping.
            field_id = change.get("fieldId") or self._jira.get_jira_issue_field_id(
                change["field"]
            )
            self._logger.debug(
                "Treating change %s for field %s" % (
                    change, field_id
                )
            )
            try:
                shotgun_field, shotgun_value = self._get_shotgun_entity_field_sync_value(
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
            self._shotgun.update(
                sg_entity["type"],
                sg_entity["id"],
                shotgun_data,
            )
            return True

        return False

    def _get_shotgun_entity_field_sync_value(self, shotgun_entity, jira_issue, jira_field_id, change):
        """
        Retrieve the Shotgun Entity field and the value to set from the given Jira
        Issue field value.

        Jira changes are expressed with a dictionary which has `toString`, `to`,
        `fromString` and `from` keys. `to` and `from` are supposed to contain
        actual values and `toString` and `fromString` their string representations.
        However, Jira does not seem to be consistent with this convention. For
        example, integer changes are not available as integer values in the `to`
        and `from` values (both are `None`), they are only available as strings
        in the `toString` and `fromString` values. So we use the string values
        or the actual values on a case by cases basis, dependending on the target
        data type.

        :param shotgun_entity: A Shotgun Entity dictionary with at least a type
                               and an id.
        :param jira_issue: A Jira Issue raw dictionary.
        :param jira_field_id: A Jira field id as a string.
        :param change: A dictionary with the field change retrieved from the
                       event change log.
        :returns: A tuple with a Jira field id and a Jira value usable for an
                  update. The returned field id is `None` if no valid field or
                  value could be retrieved.
        :raises: InvalidJiraValue if the Jira value can't be translated
                 into a valid Shotgun value.
        :raises: ValueError if the target Shotgun field is not valid.
        """

        # Retrieve the Shotgun field to update
        shotgun_field = self._get_shotgun_entity_field_for_issue_field(
            jira_field_id,
        )
        if not shotgun_field:
            self._logger.debug(
                "Don't know how to sync Jira field %s to Shotgun." % jira_field_id
            )
            return None, None

        # TODO: handle Shotgun Project specific fields?
        shotgun_field_schema = self._shotgun.get_field_schema(
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

        # Special cases for some fields where we need to perform some dedicated
        # logic.
        if jira_field_id == "assignee":
            shotgun_value = self._get_shotgun_assignment_from_jira_issue_change(
                shotgun_entity,
                shotgun_field,
                shotgun_field_schema,
                jira_issue,
                change
            )
            return shotgun_field, shotgun_value

        # General case based on the target Shotgun field data type.
        shotgun_value = self._get_shotgun_value_from_jira_change(
            shotgun_entity,
            shotgun_field,
            shotgun_field_schema,
            change,
            jira_issue["fields"][jira_field_id]
        )
        return shotgun_field, shotgun_value

    def _get_shotgun_entity_field_for_issue_field(self, jira_field_id):
        """
        Returns the Shotgun field name to use to sync the given Jira Issue field.

        Must be re-implemented in deriving classes.

        :param str jira_field_id: A Jira Issue field id, e.g. 'summary'.
        :returns: A string or `None`.
        """
        raise NotImplementedError

    def _get_shotgun_assignment_from_jira_issue_change(
        self,
        shotgun_entity,
        shotgun_field,
        shotgun_field_schema,
        jira_issue,
        change,
    ):
        """
        Retrieve a Shotgun assignment value from the given Jira change.

        This method supports single entity and multi entity Shotgun fields.

        Jira users keys are retrieved from the `from` and `to` values in the
        change dictionary.

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
                "%s field type is not valid for Shotgun %s.%s assignments. Expected "
                "entity or multi_entity." % (
                    data_type,
                    shotgun_entity["type"],
                    shotgun_field
                )
            )

        sg_valid_types = shotgun_field_schema["properties"]["valid_types"]["value"]
        if "HumanUser" not in sg_valid_types:
            raise ValueError(
                "Shotgun %s.%s assignment field must accept HumanUser but only accepts %s" % (
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
                jira_user = self._jira.user(from_assignee)
                sg_user = self._shotgun.find_one(
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
                sg_user = self._shotgun.find_one(
                    "HumanUser",
                    [["email", "is", jira_user["emailAddress"]]],
                    ["email", "name"]
                )
                if not sg_user:
                    raise InvalidJiraValue(
                        shotgun_field,
                        jira_user,
                        "Unable to retrieve a Shotgun user with email address %s" % (
                            jira_user["emailAddress"]
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
        else:  # data_type == "entity":
            if from_assignee:
                # Try to remove the old assignee from the Shotgun assignment
                jira_user = self._jira.user(from_assignee)
                sg_user = self._shotgun.find_one(
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
                sg_user = self._shotgun.find_one(
                    "HumanUser",
                    [["email", "is", jira_user["emailAddress"]]],
                    ["email", "name"]
                )
                if not sg_user:
                    raise InvalidJiraValue(
                        shotgun_field,
                        jira_user,
                        "Unable to retrieve a Shotgun user with email address %s" % (
                            jira_user["emailAddress"]
                        )
                    )
                current_sg_assignment = sg_user
        return current_sg_assignment
