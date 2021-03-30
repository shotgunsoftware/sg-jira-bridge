#!/usr/bin/env python
# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import sys
import argparse
import logging

from shotgun_api3 import Shotgun

from sg_jira import Bridge, JiraSession

logger = logging.getLogger("update_shotgun_users")


def sync_jira_users_into_shotgun(sg, jira, project_key):
    """
    Associates JIRA users with Shotgun users.

    :param sg: Connection to Shotgun
    :param jira: Connection to JIRA
    :param dict project_key: Project to use to match users.
    """

    # Let's make sure the sg_jira_account_id field exists and create it
    # if missing.
    logger.info("Ensuring HumanUser.sg_jira_account_id exists.")
    if "sg_jira_account_id" not in sg.schema_field_read("HumanUser"):
        logger.info("Creating HumanUser.sg_jira_account_id.")
        sg.schema_field_create("HumanUser", "text", "Jira Account Id")

    # Make sure the JIRA project exists.
    logger.info("Locating JIRA project %s" % project_key)
    project = jira.project(project_key)

    logger.info("Retrieving all SG users")
    users = sg.find(
        "HumanUser",
        # User's without email or with TBD (test users) should not be considered.
        [["email", "is_not", None], ["email", "is_not", "TBD"]],
        ["email", "login", "sg_jira_account_id"],
        # We sort by user id so that we always assign users in a deterministic fashion.
        # That is important because the script can be run multiple times over time
        # as a company hires more and more people.
        order=[{"field_name": "id", "direction": "asc"}],
    )
    # Track which emails have already been mapped. This needs to happen first because
    # the same email can be used for multiple users. So if an email has been mapped
    # to an account id, we'll skip all users with that email when matching.
    # This would allow an admin to run the script once, then move some JIRA account ids
    # from  one Shotgun account to another that has the same email and run the script
    # again without invalidating their work.
    mapped_emails = {
        user["email"] for user in users if user["sg_jira_account_id"] is not None
    }

    for user in users:

        # Email has already been mapped to a JIRA user, so skip it.
        if user["email"] in mapped_emails:
            logger.info(
                "The email '{}' from '{}' has already been associated with a JIRA account.".format(
                    user["email"], user["login"]
                )
            )
            continue

        # Let's try to find a JIRA user associated with that email for the given JIRA project.
        jira_user = jira.find_jira_assignee_for_issue(
            user["email"], jira_project=project
        )
        # No user was found, so skip over to the next one. The loggin from the JIRASession takes
        # care of warning the user here that no matches were found.
        if jira_user is None:
            continue

        # A JIRA user was found, so let's update SG with it's accountId!
        sg.update("HumanUser", user["id"], {"sg_jira_account_id": jira_user.accountId})
        logger.info(
            "SG user '{}' ('{}') has been matched to a JIRA user with the same email.".format(
                user["login"], user["email"]
            )
        )
        # Keep track of this new mapped email so that if we encounter it again we don't try to map
        # that user again.
        mapped_emails.add(user["email"])


def _get_settings():
    """
    Retrieves the parameters necessary to run the app, i.e. logging settings and credentials for
    both JIRA and Shotgun.

    :returns: Tuple of (log settings, )
    """
    # Parse the commend line
    parser = argparse.ArgumentParser(
        description="Matches SG users with JIRA users for JIRA Cloud.",
        epilog=(
            "This script will match the first SG user with a given email with the "
            "associated JIRA user. If for some reason there are multiple SG users "
            "with the same email, you can go back in SG and reassign the "
            "sg_jira_account_id value to the right SG user."
        ),
    )
    parser.add_argument("--settings", help="Full path to settings file.", required=True)

    parser.add_argument(
        "--project",
        type=str,
        help="The key of a JIRA project that will be synced with Shotgun.",
    )
    args = parser.parse_args()

    logger_settings, shotgun_settings, jira_settings, _ = Bridge.read_settings(
        args.settings
    )
    return logger_settings, shotgun_settings, jira_settings, args.project


def main():
    """
    Map Shotgun users to JIRA users using their respective emails.
    """
    logger_settings, shotgun_settings, jira_settings, project = _get_settings()

    # Apply settings
    if logger_settings:
        logging.config.dictConfig(logger_settings)

    # Set the logger settings first since JIRA session is chatty.
    jira = JiraSession(
        jira_settings["site"],
        basic_auth=(jira_settings["user"], jira_settings["secret"]),
    )

    if not jira.is_jira_cloud:
        logger.error("This script can be run for JIRA Cloud only.")
        return 1

    sg = Shotgun(
        shotgun_settings["site"],
        script_name=shotgun_settings["script_name"],
        api_key=shotgun_settings["script_key"],
    )

    sync_jira_users_into_shotgun(sg, jira, project)

    return 0


if __name__ == "__main__":
    sys.exit(main())
