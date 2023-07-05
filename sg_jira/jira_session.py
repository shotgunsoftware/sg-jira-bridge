# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import logging
from packaging import version

from jira import JIRAError
import jira

# Since we are using pbr in the forked jira repo, the tags we are using are marked as dev versions and
# pip doesn't update them as expected.

if version.parse(jira.__version__) < version.parse("3.5.0"):
    raise ImportError(
        "The jira version installed is too old. Make sure it is updated to 3.5.0. "
        'You can do this by using "pip install -r /path/to/requirements.txt --upgrade"'
    )

from .constants import (
    JIRA_SHOTGUN_TYPE_FIELD,
    JIRA_SHOTGUN_ID_FIELD,
    JIRA_SHOTGUN_URL_FIELD,
)
from .constants import JIRA_RESULT_PAGING

logger = logging.getLogger(__name__)


class JiraSession(jira.client.JIRA):
    """
    Extend :class:`jira.JIRA` with helpers.
    """

    def __init__(self, jira_site, *args, **kwargs):
        """
        Instantiate a JiraSession.

        Connect to the given Jira site with given parameters.

        :param str jira_site: A Jira site url.
        :raises RuntimeError: on Jira connection errors.
        """
        try:
            super(JiraSession, self).__init__(jira_site, *args, **kwargs)
        except JIRAError as e:
            # Jira puts some huge html / javascript code in the exception
            # string so we catch it to issue a more reasonable message.
            logger.debug("Unable to connect to %s: %s" % (jira_site, e), exc_info=True)
            # Check the status code
            if e.status_code == 401:
                raise RuntimeError(
                    "Unable to connect to %s (error code %d), "
                    "please check your credentials" % (jira_site, e.status_code,)
                )
            raise RuntimeError(
                "Unable to connect to %s. See the log for details." % jira_site
            )

        # accountId's are only found on JIRA Cloud. The latest version of JIRA server do not have them.
        self._is_jira_cloud = "accountId" in self.myself()
        self._account_id_field = "accountId" if self._is_jira_cloud else "key"

        logger.info(
            "Connected to %s on %s (JIRA %s)"
            % (
                self.myself()[self._account_id_field],
                jira_site,
                "Cloud" if self._is_jira_cloud else "Server",
            )
        )

        # A dictionary where keys are Jira field name and values are their field id.
        self._jira_fields_map = {}

    def setup(self):
        """
        Check the Jira site and cache site level values.

        :raises RuntimeError: if the Jira site was not correctly configured to
                 be used with this bridge.
        """
        # Build a mapping from Jira field names to their id for fast lookup.
        for jira_field in self.fields():
            self._jira_fields_map[jira_field["name"].lower()] = jira_field["id"]
        self._jira_shotgun_type_field = self.get_jira_issue_field_id(
            JIRA_SHOTGUN_TYPE_FIELD.lower()
        )
        if not self._jira_shotgun_type_field:
            raise RuntimeError(
                "Missing required custom Jira field %s" % JIRA_SHOTGUN_TYPE_FIELD
            )
        self._jira_shotgun_id_field = self.get_jira_issue_field_id(
            JIRA_SHOTGUN_ID_FIELD.lower()
        )
        if not self._jira_shotgun_id_field:
            raise RuntimeError(
                "Missing required custom Jira field %s" % JIRA_SHOTGUN_ID_FIELD
            )
        self._jira_shotgun_url_field = self.get_jira_issue_field_id(
            JIRA_SHOTGUN_URL_FIELD.lower()
        )
        if not self._jira_shotgun_url_field:
            raise RuntimeError(
                "Missing required custom Jira field %s" % JIRA_SHOTGUN_URL_FIELD
            )

    @property
    def is_jira_cloud(self):
        """
        Return if the site is a JIRA Cloud site.

        :rerturns: ``True`` if the site is hosted in the cloud, ``False`` otherwise.
        """
        return self._is_jira_cloud

    def get_jira_issue_field_id(self, name):
        """
        Return the Jira field id for the Issue field with the given name.

        :returns: The id as a string or None if the field is unknown.
        """
        return self._jira_fields_map.get(name.lower())

    @property
    def jira_shotgun_type_field(self):
        """
        Return the id of the Jira field used to store the type of a linked ShotGrid
        Entity.

        Two custom fields are used in Jira to store a reference to a ShotGrid
        Entity: its ShotGrid Entity type and id. This method returns the id of
        the Jira field used to store the ShotGrid type.
        """
        return self._jira_shotgun_type_field

    @property
    def jira_shotgun_id_field(self):
        """
        Return the id of the Jira field used to store the id of a linked ShotGrid
        Entity.

        Two custom fields are used in Jira to store a reference to a ShotGrid
        Entity: its ShotGrid Entity type and id. This method returns the id of
        the Jira field used to store the ShotGrid id.
        """
        return self._jira_shotgun_id_field

    @property
    def jira_shotgun_url_field(self):
        """
        Return the id of the Jira field used to store the url of a linked ShotGrid
        Entity.
        """
        return self._jira_shotgun_url_field

    def sanitize_jira_update_value(self, jira_value, jira_field_schema):
        """
        Perform sanity checks for the given Jira value and ensure it can be used
        to update the Jira field with the given schema.

        :returns: A Jira value which can safely be used to update the Jira field.
        :raises UserWarning: if a safe value can't be obtained.
        """
        # If the value is empty but required, check if Jira will be able to use
        # a default value. Default values are only available when creating Issues
        if not jira_value and jira_field_schema["required"]:
            # Create meta data has a "hasDefaultValue" property, edit meta data
            # does not have this property.
            has_default = jira_field_schema.get("hasDefaultValue")
            if not has_default:
                raise UserWarning(
                    "Invalid value %s: Jira field %s requires a value and does"
                    "not provide a default value"
                    % (jira_value, jira_field_schema["name"])
                )
        # Jira doesn't allow single-line text entry fields to be longer than
        # 255 characters, so we truncate the string data and add a little
        # message -- so users know to look at Shotgun. Note that this
        # "feature" could result in data loss; if the truncated text is
        # subsequently modified in Jira, the truncated result will be sent
        # to Shotgun by the Jira sync webhook.
        if jira_field_schema["schema"]["type"] == "string" and isinstance(
            jira_value, str
        ):
            # Reference:
            # com.atlassian.jira.plugin.system.customfieldtypes:textfield
            # com.atlassian.jira.plugin.system.customfieldtypes:textarea
            if (
                jira_field_schema["schema"].get("custom")
                == "com.atlassian.jira.plugin.system.customfieldtypes:textfield"
            ):
                if len(jira_value) > 255:
                    logger.warning(
                        "String data for Jira field %s is too long (> 255 chars). "
                        "Truncating for display in Jira." % jira_field_schema["name"]
                    )
                    message = "... [see Shotgun]."
                    jira_value = jira_value[: (255 - len(message))] + message

        logger.debug(
            "Sanitized Jira value for %s is %s"
            % (jira_field_schema["name"], jira_value,)
        )
        return jira_value

    def find_jira_assignee_for_issue(
        self, user_email, jira_project=None, jira_issue=None
    ):
        """
        Return a Jira user the given issue can be assigned to, based
        on the given email address.

        A Jira Project must be specified when creating an Issue. A Jira Issue must
        be specified when editing an Issue.

        :param jira_project: A :class:`jira.resources.Project` instance or None.
        :param jira_issue: A :class:`jira.Issue` instance or None.
        :param user_email: An email address as a string.
        :returns: A :class:`jira.resources.User` instance or None.
        :raises ValueError: if no Project nor Issue is specified.
        """
        return self.find_jira_user(
            user_email, jira_project, jira_issue, for_assignment=True
        )

    def _search_allowed_users_for_issue(
        self, user, project, issueKey, startAt=0, maxResults=50
    ):
        """
        Wrapper around jira.search_allowed_users_for_issue to make its parameter
        consistent with jira.search_assignable_users_for_issues parameters.
        """
        # Note: this does not work and requires a user name or email to be specified.
        # There are some various discussions about it, mentionning that using
        # "." or "%" or "_" could act as a wildcard but none of them worked.
        return self.search_allowed_users_for_issue(
            user if user else ".",
            projectKey=project.key if project else None,
            issueKey=issueKey,
            startAt=startAt,
            maxResults=maxResults,
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

    def find_jira_user(
        self, user_email, jira_project=None, jira_issue=None, for_assignment=False
    ):
        """
        Return a Jira an assignable user or with browse permission for the given
        Project or Issue, with the given email address. Either a jira_project
        or jira_issue must be provided.

        .. note:: Due to problems with user searching in Jira, this method always
                  returns assignable users for the time being.

        :param user_email: An email address as a string.
        :param jira_project: A :class:`jira.resources.Project` instance or None.
        :param jira_issue: A :class:`jira.Issue` instance or None.
        :param for_assignment: A boolean, if `False` the user just needs to have read
                            permission. If `True` the user needs to be suitable for
                            Issue assignments.
        :returns: A :class:`jira.resources.User` instance or None.
        :raises ValueError: if no Project nor Issue is specified.
        """

        if not jira_project and not jira_issue:
            raise ValueError("Either a Jira Project or a Jira Issue must be specified")

        if not user_email:
            return None

        if for_assignment:
            search_method = self.search_assignable_users_for_issues
        else:
            # See comments in _search_allowed_users_for_issue: searching for users
            # does not seem to work very well, so, for the time being, we use the
            # only method that can be trusted and only consider assignable users.
            # search_method = self._search_allowed_users_for_issue
            search_method = self.search_assignable_users_for_issues

        # Note: There is a Jira bug that prevents searching by email address from working on
        # some instances. In this case, we fall back on paging through ALL results to
        # ensure don't incorrectly miss matching the user.
        # See: https://jira.atlassian.com/browse/JRASERVER-61772
        # See: https://jira.atlassian.com/browse/JRACLOUD-61772

        # TODO: Possible source of the problem
        # Users need to have the global "Browse users and groups" permission.
        # We don't have this permission by default for some reason.
        # It's currently only assigned to the **jira-developers** group.
        # Something to double check and see if we can spot this in the setup
        # check and report the problem. And get rid of the fallback code.

        jira_assignee = None

        # Direct user search with their email
        logger.debug("Looking up %s in assignable users" % user_email)
        search_params = dict(
            project=jira_project,
            issueKey=jira_issue.key if jira_issue else None,
            maxResults=JIRA_RESULT_PAGING,
        )
        if self._is_jira_cloud:
            search_params["query"] = user_email
        else:
            search_params["username"] = user_email

        jira_users = search_method(**search_params)
        if jira_users:
            jira_assignee = jira_users[0]
            if len(jira_users) > 1:
                logger.warning(
                    "Found multiple assignable Jira users with email address %s. "
                    "Using the first one: %s"
                    % (
                        user_email,
                        [
                            "%s (%s)" % (ju.emailAddress, ju.displayName)
                            for ju in jira_users
                        ],
                    )
                )
            logger.debug("Found Jira Assignee %s" % jira_assignee)
            return jira_assignee

        # Because of the bug mentioned above, fall back on matching users ourself.
        logger.debug(
            "No assignable users found matching %s. Searching all assignable users "
            "manually" % user_email
        )
        uemail = user_email.lower()
        start_idx = 0
        logger.debug("Querying all assignable users starting at #%d" % start_idx)
        jira_users = search_method(
            startAt=start_idx,
            **search_params
        )
        while jira_users:
            for jira_user in jira_users:
                if (
                    hasattr(jira_user, "emailAddress")
                    and jira_user.emailAddress
                    and jira_user.emailAddress.lower() == uemail
                ):
                    jira_assignee = jira_user
                    break
            if jira_assignee:
                break
            else:
                start_idx += len(jira_users)
                logger.debug(
                    "Querying all assignable users starting at #%d" % start_idx
                )
                jira_users = search_method(
                    startAt=start_idx,
                    **search_params
                )
                logger.debug("Found %s users" % (len(jira_users)))

        if not jira_assignee:
            if jira_issue:
                logger.warning(
                    "Unable to find a Jira user with email %s for Issue %s"
                    % (user_email, jira_issue,)
                )
            else:
                logger.warning(
                    "Unable to find a Jira user with email %s for Project %s"
                    % (user_email, jira_project,)
                )

        logger.debug("Found Jira Assignee %s" % jira_assignee)
        return jira_assignee

    def set_jira_issue_status(self, jira_issue, jira_status_name, comment):
        """
        Attempt to change the Jira Issue status to the given value.

        Lookup for a Jira transition where the target status is the
        given one and try to apply it.

        :param jira_issue: A :class:`jira.Issue` instance.
        :param str jira_status: A Jira status name, e.g. `In Progress`.
        :param comment: A string, a comment to apply to the Jira transition.
        :return: `True` if the status could be set, `False` otherwise.
        """

        if jira_issue.fields.status.name == jira_status_name:
            logger.debug(
                "Jira issue %s status is already '%s'" % (jira_issue, jira_status_name)
            )
            return True

        # Retrieve available transitions for the issue including fields on the
        # transition screen.
        jira_transitions = self.transitions(jira_issue, expand="transitions.fields")
        for tra in jira_transitions:
            # Match a transition with the expected status name
            if tra["to"]["name"] == jira_status_name:
                logger.debug(
                    "Found transition for Jira Issue %s to %s: %s"
                    % (jira_issue, jira_status_name, tra,)
                )
                # Iterate over any fields for transition and find required fields
                # that don't have a default value. Set the value using our defaults.
                # NOTE: This only supports text fields right now.
                fields = {}
                if "fields" in tra:
                    for field_name, details in tra["fields"].items():
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
                                logger.debug(
                                    "Setting resolution to first allowedValue: %s"
                                    % details["allowedValues"][0]
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

                logger.info(
                    "Transitioning Issue %s to '%s' with params: %s"
                    % (jira_issue.key, tra["name"], params)
                )
                self.transition_issue(jira_issue, tra["id"], **params)
                return True

        logger.warning(
            "Couldn't find a Jira transition with %s as target for Issue %s"
            % (jira_status_name, jira_issue.key)
        )
        logger.debug("Available transitions are %s" % jira_transitions)
        return False

    def create_issue_from_data(self, jira_project, issue_type, data):
        """
        Create an Issue from the given data.

        Sanity check the data against Jira create meta data. Try to amend the
        data, if possible, to complete the Issue creation. Raise `ValueError` if
        the data can't be amended to complete the Issue creation.

        :param jira_project: A :class:`jira.resources.Project` instance.
        :param str issue_type: The target Issue type name.
        :param data: A dictionary where keys are Jira Issue field ids and values
                     are Jira values.
        :returns: A :class:`jira.Issue` instance.
        :raises RuntimeError: if the Jira create meta data can't be retrieved.
        :raises ValueError: if invalid and unfixable data is provided.
        """
        jira_issue_type = self.issue_type_by_name(issue_type, project=jira_project)
        # Retrieve creation meta data for the project / issue type
        # Note: there is a new simpler Project type in Jira where createmeta is not
        # available.
        # https://confluence.atlassian.com/jirasoftwarecloud/working-with-agility-boards-945104895.html
        # https://community.developer.atlassian.com/t/jira-cloud-next-gen-projects-and-connect-apps/23681/14
        # It seems a Project `simplified` key can help distinguish between old
        # school projects and new simpler projects.
        # TODO: cache the retrieved data to avoid multiple requests to the server

        if self._is_jira_cloud or self._version < (9, 0, 0):
            # Existing logic works for Jira Cloud or Jira Server 8 or prior.
            create_meta_data = self.createmeta(
                jira_project,
                issuetypeIds=jira_issue_type.id,
                expand="projects.issuetypes.fields",
            )
            # We asked for a single project / single issue type, so we can just pick
            # the first entry, if it exists.
            if (
                not create_meta_data["projects"]
                or not create_meta_data["projects"][0]["issuetypes"]
            ):
                logger.debug(
                    "Create meta data for Project %s Issue type %s: %s"
                    % (jira_project, jira_issue_type.id, create_meta_data)
                )
                raise RuntimeError(
                    "Unable to retrieve create meta data for Project %s Issue type %s."
                    % (jira_project, jira_issue_type.id,)
                )
            fields_createmeta = create_meta_data["projects"][0]["issuetypes"][0]["fields"]
        else:
            # createmeta is not supported on Jira Server 9 and Python client 3.5.0
            create_meta_data = self.createmeta_issuetypes(
                jira_project,
                expand="values.fields",
            )
            if (
                not create_meta_data["values"]
                or not create_meta_data["values"][0]["fields"]
            ):
                logger.debug(
                    "Create meta data for Project %s Issue type %s: %s"
                    % (jira_project, jira_issue_type.id, create_meta_data)
                )
                raise RuntimeError(
                    "Unable to retrieve create meta data for Project %s Issue type %s."
                    % (jira_project, jira_issue_type.id,)
                )
            fields_createmeta = create_meta_data["values"][0]["fields"]

        # Make a shallow copy so we can add/delete keys
        data = dict(data)
        data["issuetype"] = jira_issue_type.raw

        # Check if we are missing any required data which does not have a default
        # value.
        missing = []
        for k, jira_create_field in fields_createmeta.items():
            if k not in data:
                if (
                    jira_create_field["required"]
                    and not jira_create_field["hasDefaultValue"]
                ):
                    missing.append(jira_create_field["name"])
        if missing:
            raise ValueError(
                "Unable to create Jira %s Issue. The following required data is missing: %s"
                % (data["issuetype"]["name"], missing,)
            )
        # Check if we're trying to set any value which can't be set and validate
        # empty values.
        invalid_fields = []
        data_keys = list(
            data.keys()
        )  # Retrieve all keys so we can delete them in the dict
        for k in data_keys:
            # Filter out anything which can't be used in creation.
            if k not in fields_createmeta:
                logger.warning(
                    "Jira field %s cannot be set when creating an Issue. Removing it "
                    "from the request." % k
                )
                del data[k]
            elif not data[k] and fields_createmeta[k]["required"]:
                # Handle required fields with empty value
                if fields_createmeta[k]["hasDefaultValue"]:
                    # Empty field data which Jira will set default values for should be removed in
                    # order for Jira to properly set the default. Jira will complain if we leave it
                    # in.
                    logger.info(
                        "Removing Jira field %s with an empty value from data payload so "
                        "Jira will set the default value." % k
                    )
                    del data[k]
                else:
                    # Empty field data isn't valid if the field is required and doesn't have a
                    # default value in Jira.
                    invalid_fields.append(k)
        if invalid_fields:
            raise ValueError(
                "Unable to create Jira Issue. The following fields are required and cannot "
                "be empty: %s" % invalid_fields
            )

        logger.debug("Creating Jira issue with %s" % data)

        return self.create_issue(fields=data)

    def get_jira_issue_edit_meta(self, jira_issue):
        """
        Return the edit metadata for the given Jira Issue.

        :param jira_issue: A :class:`jira.Issue`.
        :returns: The Jira Issue edit metadata `fields` property.
        :raises RuntimeError: if the edit metadata can't be retrieved for the
                 given Issue.
        """
        # Retrieve edit meta data for the issue
        # TODO: cache the retrieved data to avoid multiple requests to the server
        edit_meta_data = self.editmeta(jira_issue)
        jira_edit_fields = edit_meta_data.get("fields")
        if not jira_edit_fields:
            raise RuntimeError(
                "Unable to retrieve edit meta data for %s %s. "
                % (jira_issue.fields.issuetype, jira_issue.key)
            )
        return jira_edit_fields
