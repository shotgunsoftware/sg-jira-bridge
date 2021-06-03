# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import datetime

from jira import JIRAError

from ..errors import InvalidJiraValue


class SyncHandler(object):
    """
    Base class to handle a particular sync between ShotGrid and Jira.

    Handlers typically handle syncing values between a ShotGrid Entity type and
    a Jira resource and are owned by a :class:`~sg_jira.Syncer` instance.

    This base class defines the interface all handlers should support and
    provides some helpers which can be useful to all handlers.
    """

    def __init__(self, syncer):
        """
        Instantiate a handler for the given syncer.

        :param syncer: A :class:`~sg_jira.Syncer` instance.
        """
        self._syncer = syncer

    @property
    def _logger(self):
        """
        Return the syncer logger.
        """
        return self._syncer._logger

    @property
    def _bridge(self):
        """
        Return a connected :class:`~sg_jira.Bridge` instance.
        """
        return self._syncer.bridge

    @property
    def _shotgun(self):
        """
        Return a connected :class:`~sg_jira.shotgun_session.ShotgunSession` instance.
        """
        return self._syncer.shotgun

    @property
    def _jira(self):
        """
        Return a connected :class:`~sg_jira.jira_session.JiraSession` instance.
        """
        return self._syncer.jira

    @property
    def _sg_jira_status_mapping(self):
        """
        Needs to be re-implemented in deriving classes and return a dictionary
        where keys are ShotGrid status short codes and values are Jira status
        names, or any string value which should be mapped to ShotGrid status.
        """
        raise NotImplementedError

    def get_jira_project(self, project_key):
        """
        Retrieve the Jira Project with the given key, if any.

        :returns: A :class:`jira.resources.Project` instance or None.
        """
        return self._syncer.get_jira_project(project_key)

    def get_jira_issue(self, issue_key):
        """
        Retrieve the Jira Issue with the given key, if any.

        :param str issue_key: A Jira Issue key to look for.
        :returns: A :class:`jira.Issue` instance or None.
        :raises RuntimeError: if the Issue if not bound to any Project.
        """
        jira_issue = None
        try:
            jira_issue = self._jira.issue(issue_key)
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

    def setup(self):
        """
        This method can be re-implemented in deriving classes to Check the Jira
        and ShotGrid site, ensure that the sync can safely happen and cache any
        value which is slow to retrieve.

        This base implementation does nothing.
        """
        pass

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given ShotGrid Entity.

        Must be re-implemented in deriving classes.

        :returns: `True` if the event is accepted for processing, `False` otherwise.
        """
        raise NotImplementedError

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given ShotGrid event for the given ShotGrid Entity

        Must be re-implemented in deriving classes.

        :param str entity_type: The ShotGrid Entity type to sync.
        :param int entity_id: The id of the ShotGrid Entity to sync.
        :param event: A dictionary with the event for the change.
        :returns: True if the event was successfully processed, False if the
                  sync didn't happen for any reason.
        """
        raise NotImplementedError

    def accept_jira_event(self, resource_type, resource_id, event):
        """
        Accept or reject the given event for the given Jira resource.

        Must be re-implemented in deriving classes.

        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event is accepted for processing, False otherwise.
        """
        raise NotImplementedError

    def process_jira_event(self, resource_type, resource_id, event):
        """
        Process the given Jira event for the given Jira resource.

        Must be re-implemented in deriving classes.

        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event was successfully processed, False if the
                  sync didn't happen for any reason.
        """
        raise NotImplementedError

    def _get_shotgun_value_from_jira_change(
        self, shotgun_entity, shotgun_field, shotgun_field_schema, change, jira_value,
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
        :param jira_value: The full current Jira value.
        :raises RuntimeError: if the Shotgun Entity can't be retrieved from Shotgun.
        :raises ValueError: for unsupported Shotgun data types.
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
                "Updating SG %s.%s schema with valid values: %s"
                % (shotgun_entity["type"], shotgun_field, all_allowed)
            )
            self._shotgun.schema_field_update(
                shotgun_entity["type"], shotgun_field, {"valid_values": all_allowed}
            )
            # Clear the schema to take into account the change we just made.
            self._shotgun.clear_cached_field_schema(shotgun_entity["type"])
            return value

        if data_type == "status_list":
            value = change["toString"]
            if not value:
                # Unset the status in Shotgun
                return None
            # Look up a matching Shotgun status from our mapping
            # Please note that if we have multiple matching values the first
            # one will be arbitrarily returned.
            for sg_code, jira_name in self._sg_jira_status_mapping.items():
                if value.lower() == jira_name.lower():
                    return sg_code
            # No match.
            raise InvalidJiraValue(
                shotgun_field,
                value,
                "Unable to find a matching SG status for %s from %s"
                % (value, self._sg_jira_status_mapping),
            )

        if data_type == "multi_entity":
            # If the Jira field is an array we will get the list of resource
            # names in a string, separated by spaces.
            # We're assuming here that if someone maps a Jira simple field to
            # a Shotgun multi entity field the same convention will be applied
            # and spaces will be used as separators.
            allowed_entities = shotgun_field_schema["properties"]["valid_types"][
                "value"
            ]
            old_list = set()
            new_list = set()
            if change["fromString"]:
                old_list = set(change["fromString"].split(" "))
            if change["toString"]:
                new_list = set(change["toString"].split(" "))
            removed_list = old_list - new_list
            added_list = new_list - old_list
            # Make sure we have the current value and the Shotgun project
            consolidated = self._shotgun.consolidate_entity(
                shotgun_entity, fields=[shotgun_field, "project"]
            )
            if not consolidated:
                raise RuntimeError(
                    "Unable to find %s (%d) in Shotgun"
                    % (shotgun_entity["type"], shotgun_entity["id"])
                )
            current_sg_value = consolidated[shotgun_field]
            for removed in removed_list:
                # Try to remove the entries from the Shotgun value. We make a
                # copy of the list so we can delete entries while iterating
                self._logger.debug(
                    "Trying to remove %s from SG %s value %s"
                    % (removed, shotgun_field, current_sg_value,)
                )
                for i, sg_value in enumerate(list(current_sg_value)):
                    # Match the SG entity name, because this is retrieved
                    # from the entity holding the list, we do have a "name" key
                    # even if the linked Entities use another field to store their
                    # name e.g. "code"
                    if removed.lower() == sg_value["name"].lower():
                        self._logger.debug(
                            "Removing %s from SG value %s since Jira "
                            "removed %s " % (sg_value, current_sg_value, removed,)
                        )
                        del current_sg_value[i]
            for added in added_list:
                # Check if the value is already there
                self._logger.debug(
                    "Trying to add %s to SG %s value %s"
                    % (added, shotgun_field, current_sg_value,)
                )
                for sg_value in current_sg_value:
                    # Match the SG entity name, because this is retrieved
                    # from the entity holding the list, we do have a "name" key
                    # even if the linked Entities use another field to store their
                    # name e.g. "code"
                    if added.lower() == sg_value["name"].lower():
                        self._logger.debug(
                            "%s is already in current SG value: %s" % (added, sg_value,)
                        )
                        break
                else:
                    # We need to retrieve a matching Entity from Shotgun and
                    # add it to the list, if we found one.
                    sg_value = self._shotgun.match_entity_by_name(
                        added, allowed_entities, consolidated["project"]
                    )
                    if sg_value:
                        self._logger.debug(
                            "Adding %s to SG value %s since Jira "
                            "added %s" % (sg_value, current_sg_value, added,)
                        )
                        current_sg_value.append(sg_value)
                    else:
                        self._logger.warning(
                            "Couldn't find a %s named '%s' in Shotgun"
                            % (" or ".join(allowed_entities), added)
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
                message = "Unable to parse Jira value %s as a date: %s" % (value, e)
                # Log the original error with a traceback for debug purpose
                self._logger.debug(
                    message, exc_info=True,
                )
                # Notify the caller that the value is not right
                raise InvalidJiraValue(shotgun_field, value, message)
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
                message = "Jira value %s is not a valid integer: %s" % (value, e)
                # Log the original error with a traceback for debug purpose
                self._logger.debug(
                    message, exc_info=True,
                )
                # Notify the caller that the value is not right
                raise InvalidJiraValue(shotgun_field, value, message)

        if data_type == "checkbox":
            return bool(change["toString"])

        raise ValueError(
            "Unsupported data type %s for %s.%s change from Jira update: %s"
            % (data_type, shotgun_entity["type"], shotgun_field, change)
        )
