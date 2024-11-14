# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import jira

from sg_jira.errors import InvalidShotgunValue


class JiraHook(object):

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

    def get_jira_value_from_sg_value(self, sg_value, jira_issue, jira_field, jira_field_properties, skip_array_check=False):
        """"""

        self._logger.debug(f"Getting Jira value for Flow Production Tracking value {sg_value}")

        jira_field_type = jira_field_properties["schema"]["type"]
        is_array = jira_field_properties["schema"]["type"] == "array"
        jira_value = self.get_jira_default_value(jira_field_type) if not sg_value else sg_value

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
            jira_value = self._jira.find_jira_assignee_for_issue(email_address, jira_issue.fields.project, jira_issue)

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
            jira_value = self._jira.sanitize_jira_update_value(jira_value, jira_field_properties)
        except UserWarning as e:
            self._logger.warning(e)
            return None

        return jira_value

    @staticmethod
    def get_jira_default_value(jira_field_type):
        """"""
        if jira_field_type == "string":
            return ""

        if jira_field_type == "timetracking":
            # We need to provide a null estimate, otherwise Jira will error
            # out.
            return 0

        return None

    def get_jira_value_from_sg_list(self, sg_value, jira_issue, jira_field, jira_field_properties):
        """"""

        is_array = jira_field_properties["schema"]["type"] == "array"

        # first case, the jira field is also a list so we're going to map each value
        if is_array:
            jira_value = []
            for v in sg_value:
                jv = self.get_jira_value_from_sg_value(v, jira_issue, jira_field, jira_field_properties, skip_array_check=True)
                if jv is not None:
                    jira_value.append(jv)

        # second case, the jira field isn't a list so we have to take the first value of the FPTR list
        else:
            jira_value = self.get_jira_value_from_sg_value(
                sg_value[0] if len(sg_value) > 0 else None,
                jira_issue,
                jira_field,
                jira_field_properties
            )

        return jira_value
