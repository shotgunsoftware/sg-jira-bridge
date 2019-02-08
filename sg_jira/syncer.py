# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import datetime
import logging
from jira import JIRAError
import jira

from .errors import InvalidShotgunValue, InvalidJiraValue


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
    def handlers(self):
        """
        Needs to be re-implemented in deriving classes and return a list of
        :class:`SyncHandler` instances.
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


    def get_shotgun_entity_field_sync_value(self, shotgun_entity, jira_issue, jira_field_id, change):
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
        shotgun_field_schema = self.shotgun.get_field_schema(
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
            shotgun_value = self.get_shotgun_assignment_from_jira_issue_change(
                shotgun_entity,
                shotgun_field,
                shotgun_field_schema,
                jira_issue,
                change
            )
            return shotgun_field, shotgun_value

        # General case based on the target Shotgun field data type.
        shotgun_value = self.get_shotgun_value_from_jira_issue_change(
            shotgun_entity,
            shotgun_field,
            shotgun_field_schema,
            change,
            jira_issue["fields"][jira_field_id]
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
                    raise InvalidJiraValue(
                        shotgun_field,
                        jira_user,
                        "Unable to retrieve a Shotgun user with email address %s" % (
                            jira_user["emailAddress"]
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
        jira_value,
    ):
        """
        Return a Shotgun value suitable to update the given Shotgun Entity field
        from the given Jira change.

        The following Shotgun field types are supported by this method:
        - text
        - list
        - status_list
        - multi_entity
        - date
        - duration
        - number
        - checkbox

        :param str shotgun_entity: A Shotgun Entity dictionary as retrieved from
                                   Shotgun.
        :param str shotgun_field: The Shotgun Entity field to get a value for.
        :param shotgun_field_schema: The Shotgun Entity field schema.
        :param change: A Jira event changelog dictionary with 'fromString',
                       'toString', 'from' and 'to' keys.
        :raises: RuntimeError if the Shotgun Entity can't be retrieved from Shotgun.
        :raises: ValueError for unsupported Shotgun data types.
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
            # values on both side could be very painful. Another option here
            # would be to raise an InvalidJiraValue
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
            self.shotgun.clear_cached_field_schema(shotgun_entity["type"])
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
            raise InvalidJiraValue(
                shotgun_field,
                value,
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
            consolidated = self.shotgun.consolidate_entity(
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
                    sg_value = self.shotgun.match_entity_by_name(
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

        if data_type == "date":
            # We use the "to" value here as the toString value includes some
            # time with the date e.g. "2019-01-31 00:00:00.0"
            value = change["to"]
            if not value:
                return None
            try:
                # Validate the date string
                datetime.datetime.strptime(value, "%Y-%m-%d")
            except ValueError as e:
                message = "Unable to parse %s as a date: %s" % (
                    value, e
                )
                # Log the original error with a traceback for debug purpose
                self._logger.debug(
                    message,
                    exc_info=True,
                )
                # Notify the caller that the value is not right
                raise InvalidJiraValue(
                    shotgun_field,
                    value,
                    message
                )
            return value

        if data_type in ["duration", "number"]:
            # Note: int Jira field changes are not available from the "to" key.
            value = change["toString"]
            if value is None:
                return None
            # Validate the int value
            try:
                return int(value)
            except ValueError as e:
                message = "%s is not a valid integer: %s" % (
                    value, e
                )
                # Log the original error with a traceback for debug purpose
                self._logger.debug(
                    message,
                    exc_info=True,
                )
                # Notify the caller that the value is not right
                raise InvalidJiraValue(
                    shotgun_field,
                    value,
                    message
                )

        if data_type == "checkbox":
            return bool(change["toString"])

        raise ValueError(
            "Unsupported data type %s for %s.%s change %s" % (
                data_type,
                shotgun_entity["type"],
                shotgun_field,
                change
            )
        )

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :returns: A :class:`SyncHandler` instance if the event is accepted for
                  processing, `None` otherwise.
        """

        # Sanity check the event before checking with handlers
        # We require a non empty event.
        if not event:
            return None

        # Check we have a Project
        if not event.get("project"):
            self._logger.debug("Rejecting event %s with no project." % event)
            return None

        # Check the event meta data
        meta = event.get("meta")
        if not meta:
            self._logger.debug("Rejecting event %s with no meta data." % event)
            return None

        if meta.get("type") != "attribute_change":
            self._logger.debug(
                "Rejecting event %s with wrong or missing event type." % event
            )
            return None

        field = meta.get("attribute_name")
        if not field:
            self._logger.debug(
                "Rejecting event %s with missing attribute name." % (
                    event
                )
            )
            return None

        # Check we didn't trigger the event to avoid infinite loops.
        user = event.get("user")
        current_user = self._bridge.current_shotgun_user
        if user and current_user:
            if user["type"] == current_user["type"] and user["id"] == current_user["id"]:
                self._logger.debug("Rejecting event %s created by us." % event)
                return None

        # Loop over all handlers and return the first one which accepts the
        # event for the given entity
        for handler in self.handlers:
            if handler.accept_shotgun_event(entity_type, entity_id, event):
                return handler

        return None

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
