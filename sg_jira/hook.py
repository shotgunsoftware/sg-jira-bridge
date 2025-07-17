# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import datetime
import re

import jira

from sg_jira.errors import InvalidJiraValue, InvalidShotgunValue


class JiraHook(object):
    """Hook class that can be inherited by the user so he'd be able to override/customize methods"""

    # This will match JIRA accounts in the following format
    # 123456:uuid, e.g. 123456:60e119d8-6a49-4375-95b6-6740fc8e75e0
    # 24 hexdecimal characters: 5b6a25ab7c14b729f2208297
    # We're only matching the first 20 characters instead of the first 24, since the
    # account id format isn't documented.
    # It could in theory match a very long user name that uses hexadecimal characters
    # only, but that would be unlikely.
    # https://regex101.com/r/E1ysHQ/1
    ACCOUNT_ID_RE = re.compile("^[0-9a-f:-]{20}")

    # Template used to build Jira comments body from a Note.
    COMMENT_BODY_TEMPLATE = """
    {panel:title=%s}
    _Note created from FPTR by %s_
    %s
    {panel}
    """

    # Associated regex used to get FPTR Note information from Jira comment body
    JIRA_COMMENT_REGEX = r"{panel:bgColor=#[\w]{6}}\n\*(.*)\*\n\n_Note created from FPTR by ([\w\s]+)_\n(.*)\n{panel}"

    # Template used to build Jira worklogs content from a TimeLog.
    WORKLOG_BODY_TEMPLATE = """
    _Worklog created from FPTR by %s_
    %s
    """

    # Associated regex used to get FPTR TimeLog information from Jira worklog body
    JIRA_WORKLOG_REGEX = r"_Worklog created from FPTR by ([\w\s]+)_\n(.*)"

    # Define the format of the Flow Production Tracking dates
    SG_DATE_FORMAT = "%Y-%m-%d"

    # Define the format of the Jira dates
    JIRA_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"

    def __init__(self, bridge, logger):
        """Class constructor"""
        super(JiraHook, self).__init__()
        self._bridge = bridge
        self._logger = logger

    @property
    def _shotgun(self):
        return self._bridge.shotgun

    @property
    def _jira(self):
        return self._bridge.jira

    def get_jira_value_from_sg_value(
        self,
        sg_value,
        jira_entity,
        jira_field,
        jira_field_properties,
        skip_array_check=False,
    ):
        """
        Helper method to convert a FPTR field value to a Jira field value.
        :param sg_value: The FPTR field value to convert.
        :param jira_entity: The Jira entity we want to get the value for.
        :param jira_field: The Jira field we want to get the value for.
        :param jira_field_properties: Properties of the Jira field we want to get hte value for.
        :param skip_array_check: If True, will skip some extra Jira formatting if the FPTR field is an array.
        :returns: The Jira field value.
        """

        self._logger.debug(
            f"Getting Jira value for Flow Production Tracking value {sg_value}"
        )

        # if we're facing some custom use cases (FPTR TimeLog vs Jira Worklog for example)
        # we want to force the returned value
        if isinstance(jira_entity, jira.resources.Worklog):
            if jira_field == "timeSpentSeconds":
                return sg_value * 60
            if jira_field == "started":
                return self.format_jira_date(sg_value)
            return sg_value

        jira_field_type = jira_field_properties["schema"]["type"]
        is_array = jira_field_properties["schema"]["type"] == "array"
        jira_value = (
            self.get_jira_default_value(jira_field_type) if not sg_value else sg_value
        )

        if isinstance(sg_value, dict):
            # Assume a FPTR Entity
            jira_value = self._shotgun.consolidate_entity(sg_value)

        # in most simple cases the Jira value is the Shotgun value, but we may face some particular cases
        if jira_field in ["assignee", "reporter"]:
            if isinstance(jira_value, dict):
                email_address = jira_value.get("email")
                if not email_address:
                    self._logger.warning(
                        f"Jira field {jira_field} requires an email address but Flow Production Tracking "
                        f"value to sync has no email key {sg_value}"
                    )
                    return None
            else:
                email_address = jira_value
            jira_value = self._jira.find_jira_assignee_for_issue(
                email_address, jira_entity.fields.project, jira_entity
            )

        elif jira_field == "labels":
            if isinstance(jira_value, dict):
                jira_value = jira_value["name"]
            # Jira does not accept spaces in labels.
            # Note: we could try to sanitize the data with "_" but then we
            # could end up having conflicts when syncing back the sanitized
            # value from Jira. Seems safer to just not sync it.
            if " " in jira_value:
                raise InvalidShotgunValue(
                    jira_field, jira_value, "Jira labels can't contain spaces"
                )

        elif jira_field == "summary":
            # JIRA raises an error if there are new line characters in the
            # summary for an Issue.
            jira_value = jira_value.replace("\n", "").replace("\r", "")

        elif jira_field == "timetracking":
            # Note: time tracking needs to be enabled in Jira
            # https://confluence.atlassian.com/adminjiracloud/configuring-time-tracking-818578858.html
            # And it does not seem that this available with new default
            # Kanban board...
            jira_value = {"originalEstimate": "%d m" % jira_value}

        # TODO: check allowed values
        allowed_values = jira_field_properties.get("allowedValues")
        if allowed_values:
            pass

        if isinstance(jira_value, jira.resources.Resource):
            # jira.Resource instances are not json serializable so we need
            # to return their raw value
            jira_value = jira_value.raw

        if is_array and not skip_array_check:
            # Single Shotgun value mapped to Jira list value
            jira_value = [jira_value] if jira_value else []

        # finally, sanitize the jira value
        try:
            jira_value = self._jira.sanitize_jira_update_value(
                jira_value, jira_field_properties
            )
        except UserWarning as e:
            self._logger.warning(e)
            return None

        return jira_value

    @staticmethod
    def get_jira_default_value(jira_field_type):
        """
        Returns the default value for the given Jira field type.
        """
        if jira_field_type == "string":
            return ""

        if jira_field_type == "timetracking":
            # We need to provide a null estimate, otherwise Jira will error
            # out.
            return 0

        return None

    def get_jira_value_from_sg_list(
        self, sg_value, jira_entity, jira_field, jira_field_properties
    ):
        """
        Convert a FPTR list value into a Jira field value that is compatible.
        :param sg_value: The FPTR field value to convert.
        :param jira_entity: The Jira entity we want to get the value for.
        :param jira_field: The Jira field we want to get the value for.
        :param jira_field_properties: Properties of the Jira field we want to get hte value for.
        :returns: The Jira field value.
        """

        is_array = jira_field_properties["schema"]["type"] == "array"

        # first case, the jira field is also a list so we're going to map each value
        if is_array:
            jira_value = []
            for v in sg_value:
                jv = self.get_jira_value_from_sg_value(
                    v,
                    jira_entity,
                    jira_field,
                    jira_field_properties,
                    skip_array_check=True,
                )
                if jv is not None:
                    jira_value.append(jv)

        # second case, the jira field isn't a list so we have to take the first value of the FPTR list
        else:
            jira_value = self.get_jira_value_from_sg_value(
                sg_value[0] if len(sg_value) > 0 else None,
                jira_entity,
                jira_field,
                jira_field_properties,
            )

        return jira_value

    def get_sg_value_from_jira_value(
        self, jira_value, jira_entity, sg_project, sg_field_properties
    ):
        """
        Convert a Jira field value into a FPTR field value that is compatible.
        :param jira_value: The Jira field value to convert.
        :param jira_entity: The Jira entity we want to convert the value from.
        :param sg_project: FPTR project the entity we're trying to get the value for belongs to.
        :param sg_field_properties: Properties of the FPTR field we want to get the value for.
        :returns: The FPTR field value.
        """

        sg_field = sg_field_properties["name"]["value"]

        data_type = sg_field_properties["data_type"]["value"]
        if data_type == "text":
            return jira_value if jira_value else ""

        if data_type == "list":
            # TODO: based on the previous behavior, if the Jira value we're trying to push to FPTR list doesn't exist
            #  in the list, the new value will be added
            #  do we want to keep this behavior and modify the list values on the fly? or should we raise an
            #  error/exception/message to let the user that the value is trying to sync doesn't exist in FPTR
            return jira_value if jira_value else ""

        if data_type in ["multi_entity", "entity"]:
            if not jira_value:
                return [] if data_type == "multi_entity" else None
            # Jira field might contain a single entity and be mapped to a FPTR multi-entity field
            if not isinstance(jira_value, list):
                jira_value = [jira_value]
            allowed_entities = sg_field_properties["properties"]["valid_types"]["value"]
            sg_entities = []
            for entity_name in jira_value:
                if isinstance(entity_name, jira.resources.User):
                    sg_value = self.get_sg_user_from_jira_user(entity_name)
                else:
                    sg_value = self._shotgun.match_entity_by_name(
                        entity_name, allowed_entities, sg_project
                    )
                if not sg_value:
                    # TODO: do we want to enable entity creation when syncing
                    continue
                sg_entities.append(sg_value)
            if data_type == "entity" and len(sg_entities) > 0:
                return sg_entities[0]
            return sg_entities

        if data_type == "date":
            # Jira dates are stored as string
            if not jira_value:
                return None
            try:
                if isinstance(jira_entity, jira.resources.Worklog):
                    return self.format_sg_date(jira_value)
                # Validate the date string
                datetime.datetime.strptime(jira_value, "%Y-%m-%d")
            except ValueError:
                # Notify the caller that the value is not right
                raise InvalidJiraValue(
                    sg_field,
                    jira_value,
                    "Unable to parse Jira value %s as a date." % jira_value,
                )
            return jira_value

        if data_type in ["duration", "number"]:
            if not jira_value:
                return 0
            elif isinstance(jira_entity, jira.resources.Worklog):
                jira_value = jira_value / 60
            try:
                return int(jira_value)
            except ValueError:
                raise InvalidJiraValue(
                    sg_field, jira_value, "Unable to parse Jira value as integer"
                )

        if data_type == "checkbox":
            return bool(jira_value)

        raise ValueError(
            f"Unable to parse Jira value: invalid FPTR data type {data_type}"
        )

    def get_sg_user_from_jira_user(self, jira_user):
        """
        Given a Jira user, returns the associated FPTR user.
        """

        if self._jira.is_jira_cloud:
            sg_filters = [["sg_jira_account_id", "is", jira_user.accountId]]
        else:
            sg_filters = [["email", "is", jira_user.emailAddress]]

        if not sg_filters:
            raise ValueError(
                f"Couldn't find valid FPTR filters to get the user associated to this Jira user {jira_user}"
            )

        return self._shotgun.find_one("HumanUser", sg_filters, ["id", "email", "name"])

    def compose_jira_comment_body(self, sg_note):
        """Helper method to compose the Jira comment body from a FPTR note."""
        return self.COMMENT_BODY_TEMPLATE % (
            sg_note["subject"],
            sg_note["user"]["name"],
            sg_note["content"],
        )

    def extract_jira_comment_data(self, jira_comment_body):
        """Helper method to extract the FPTR note data from a Jira comment body."""

        result = re.search(self.JIRA_COMMENT_REGEX, jira_comment_body, flags=re.S)

        # if the Jira comment body doesn't match our regex, that means the comment could have been created from Jira
        # so the data will be found from the comment itself rather than its body
        if not result:
            return None, jira_comment_body, None

        author = result.group(2).strip()
        # we need to make sure the author is associated with a current FPTR user
        sg_user = self._shotgun.find_one("HumanUser", [["name", "is", author]])
        if not sg_user:
            raise InvalidJiraValue(
                "content",
                jira_comment_body,
                "Invalid Jira Comment panel formatting. Unable to parse FPTR "
                "author from '%s'" % author,
            )

        subject = result.group(1).strip()
        # if we have any { or } in the title reject the value as it is likely
        # to be an ill-formed panel block.
        if re.search(r"[\{\}]", subject):
            raise InvalidJiraValue(
                "content",
                jira_comment_body,
                "Invalid Jira Comment panel formatting. Unable to parse FPTR "
                "subject from '%s'" % subject,
            )
        content = result.group(3).strip()

        return subject, content, sg_user

    def compose_jira_worklog_comment(self, sg_timelog):
        """Helper method to compose the Jira Worklog comment from a FPTR timelog."""
        return self.WORKLOG_BODY_TEMPLATE % (
            sg_timelog["user"]["name"],
            sg_timelog.get("description", ""),
        )

    def extract_jira_worklog_data(self, jira_worklog_comment):
        """Helper method to extract the FPTR timelog data from a Jira Worklog comment."""

        result = re.search(self.JIRA_WORKLOG_REGEX, jira_worklog_comment, flags=re.S)

        # if the Jira comment body doesn't match our regex, that means the comment could have been created from Jira
        # so the data will be found from the comment itself rather than its body
        if not result:
            return jira_worklog_comment, None

        author = result.group(1).strip()
        # we need to make sure the author is associated with a current FPTR user
        sg_user = self._shotgun.find_one("HumanUser", [["name", "is", author]])
        if not sg_user:
            raise InvalidJiraValue(
                "content",
                jira_worklog_comment,
                "Invalid Jira Worklog comment formatting. Unable to parse FPTR "
                "author from '%s'" % author,
            )

        return result.group(2).strip(), sg_user

    def format_jira_date(self, sg_date):
        """Helper method to convert a FPTR date into a Jira date."""
        jira_formatted_date = self.JIRA_DATE_FORMAT.replace("%f", "000").replace(
            "%z", "+0000"
        )
        return datetime.datetime.strptime(sg_date, self.SG_DATE_FORMAT).strftime(
            jira_formatted_date
        )

    def format_sg_date(self, jira_date):
        """Helper method to convert a Jira date into a FPTR date."""
        return datetime.datetime.strptime(jira_date, self.JIRA_DATE_FORMAT).strftime(
            self.SG_DATE_FORMAT
        )
