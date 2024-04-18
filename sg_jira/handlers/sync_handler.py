# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import datetime
import re

from jira import JIRAError

from ..errors import InvalidJiraValue


class SyncHandler(object):
    """
    Base class to handle a particular sync between Flow Production Tracking and Jira.

    Handlers typically handle syncing values between a Flow Production Tracking Entity type and
    a Jira resource and are owned by a :class:`~sg_jira.Syncer` instance.

    This base class defines the interface all handlers should support and
    provides some helpers which can be useful to all handlers.
    """

    # This will match JIRA accounts in the following format
    # 123456:uuid, e.g. 123456:60e119d8-6a49-4375-95b6-6740fc8e75e0
    # 24 hexdecimal characters: 5b6a25ab7c14b729f2208297
    # We're only matching the first 20 characters instead of the first 24, since the
    # account id format isn't documented.
    # It could in theory match a very long user name that uses hexadecimal characters
    # only, but that would be unlikely.
    # https://regex101.com/r/E1ysHQ/1
    ACCOUNT_ID_RE = re.compile("^[0-9a-f:-]{20}")

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
        where keys are Flow Production Tracking status short codes and values are Jira status
        names, or any string value which should be mapped to Flow Production Tracking status.
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

    def get_jira_user(self, user_email, jira_project):
        """
        Given an email address, find the associated Jira User in the given Jira Project.

        :param user_email: The email address of the user we want to retrieve
        :param jira_project: An instance of :class:`jira.resources.Project` we want to retrieve the user from
        :returns: A :class:`jira.resources.User` instance or None.
        """

        reporter = None

        jira_user = self._jira.find_jira_user(
            user_email,
            jira_project=jira_project,
        )

        # If we found a Jira user, use his name as the reporter name,
        # otherwise use the reporter name retrieved from the user used
        # to run the bridge.
        if jira_user:
            # Jira Cloud no longer supports the name field and Jira server does not support
            # accountId. So we need different behaviour based on the type of Jira we're using
            if self._jira.is_jira_cloud:
                reporter = {"accountId": jira_user.accountId}
            else:
                reporter = {"name": jira_user.name}

        return reporter

    def get_sg_user(self, user_id, jira_user=None):
        """
        Resolve the Flow Production Tracking user associated to the JIRA user passed in.

        :param str user_id: Value of the to or from of a JIRA changelog.
        :param dict jira_user: User resource, typically the assignee field on an issue. Can be None

        :returns: A FPTR user entity dictionary or None
        """

        # Due to GDPR, some changes were done to JIRA Cloud which complicates
        # matching users by email. So let's use the right resolver based
        # on the server type.
        if self._jira.is_jira_cloud:

            sg_field = "sg_jira_account_id"
            sg_value = user_id

            if jira_user is not None:
                sg_value = jira_user["accountId"]

            # jira_user is None when the user resolving code is trying to resolve the `from` user in the changelog.
            # When this happens, we only have a user id in the `from` to indicate what the original value was.
            #
            # Interestingly, when the user field is updated via the JIRA API,
            # the username is passed in instead of the account id in the `from` field, so we'll have to
            # resolve it.
            elif self.ACCOUNT_ID_RE.match(user_id) is None:
                self._logger.debug(
                    "The changelog's to/from contains a user name. accountId will be retrieved."
                )
                user = self._jira.user(user_id, payload="key")
                if not user:
                    self._logger.debug("Unable to find JIRA user %s" % user_id)
                    return None
                sg_value = user.accountId

        else:

            sg_field = "email"

            if jira_user is not None:
                sg_value = jira_user["emailAddress"]
            elif user_id is not None:
                sg_value = self._jira.user(user_id).emailAddress
            else:
                # The code that calls this method should always have a user passed in. If there is not
                # user_id or jira_user value, we shouldn't even be calling this method in the first
                # place!
                raise RuntimeError("jira_user or user_id cannot be both None.")

        sg_user = self._shotgun.find_one(
            "HumanUser", [[sg_field, "is", sg_value]], ["email", "name"]
        )
        if not sg_user:
            self._logger.debug(
                "Unable to find a Shotgun user with %s %s" % (sg_field, sg_value)
            )
        return sg_user

    def setup(self):
        """
        This method can be re-implemented in deriving classes to Check the Jira
        and Flow Production Tracking site, ensure that the sync can safely happen and cache any
        value which is slow to retrieve.

        This base implementation does nothing.
        """
        pass

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Flow Production Tracking Entity.

        Must be re-implemented in deriving classes.

        :returns: `True` if the event is accepted for processing, `False` otherwise.
        """
        raise NotImplementedError

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Flow Production Tracking event for the given Flow Production Tracking Entity

        Must be re-implemented in deriving classes.

        :param str entity_type: The Flow Production Tracking Entity type to sync.
        :param int entity_id: The id of the Flow Production Tracking Entity to sync.
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
        self,
        shotgun_entity,
        shotgun_field,
        shotgun_field_schema,
        change,
        jira_value,
    ):
        """
        Return a Flow Production Tracking value suitable to update the given Flow Production Tracking Entity field
        from the given Jira change.

        The following Flow Production Tracking field types are supported by this method:
        - text
        - list
        - status_list
        - multi_entity
        - date
        - duration
        - number
        - checkbox

        :param str shotgun_entity: A Flow Production Tracking Entity dictionary as retrieved from
                                   Flow Production Tracking.
        :param str shotgun_field: The Flow Production Tracking Entity field to get a value for.
        :param shotgun_field_schema: The Flow Production Tracking Entity field schema.
        :param change: A Jira event changelog dictionary with 'fromString',
                       'toString', 'from' and 'to' keys.
        :param jira_value: The full current Jira value.
        :raises RuntimeError: if the Flow Production Tracking Entity can't be retrieved from Flow Production Tracking.
        :raises ValueError: for unsupported Flow Production Tracking data types.
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
                "Updating Shotgun %s.%s schema with valid values: %s"
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
                "Unable to find a matching Shotgun status for %s from %s"
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
                    "Trying to remove %s from Shotgun %s value %s"
                    % (
                        removed,
                        shotgun_field,
                        current_sg_value,
                    )
                )
                for i, sg_value in enumerate(list(current_sg_value)):
                    # Match the PTR entity name, because this is retrieved
                    # from the entity holding the list, we do have a "name" key
                    # even if the linked Entities use another field to store their
                    # name e.g. "code"
                    if removed.lower() == sg_value["name"].lower():
                        self._logger.debug(
                            "Removing %s from Shotgun value %s since Jira "
                            "removed %s "
                            % (
                                sg_value,
                                current_sg_value,
                                removed,
                            )
                        )
                        del current_sg_value[i]
            for added in added_list:
                # Check if the value is already there
                self._logger.debug(
                    "Trying to add %s to Shotgun %s value %s"
                    % (
                        added,
                        shotgun_field,
                        current_sg_value,
                    )
                )
                for sg_value in current_sg_value:
                    # Match the PTR entity name, because this is retrieved
                    # from the entity holding the list, we do have a "name" key
                    # even if the linked Entities use another field to store their
                    # name e.g. "code"
                    if added.lower() == sg_value["name"].lower():
                        self._logger.debug(
                            "%s is already in current Shotgun value: %s"
                            % (
                                added,
                                sg_value,
                            )
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
                            "Adding %s to Shotgun value %s since Jira "
                            "added %s"
                            % (
                                sg_value,
                                current_sg_value,
                                added,
                            )
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
                    message,
                    exc_info=True,
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
                    message,
                    exc_info=True,
                )
                # Notify the caller that the value is not right
                raise InvalidJiraValue(shotgun_field, value, message)

        if data_type == "checkbox":
            return bool(change["toString"])

        raise ValueError(
            "Unsupported data type %s for %s.%s change from Jira update: %s"
            % (data_type, shotgun_entity["type"], shotgun_field, change)
        )
