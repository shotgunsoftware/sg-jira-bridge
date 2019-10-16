# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import argparse
import logging

from shotgun_api3 import Shotgun

from sg_jira import Bridge, JiraSession


def sync_jira_users_into_shotgun(sg, jira, project_key):
    """
    Associates JIRA users with Shotgun users.
    """
    print("Ensuring HumanUser.sg_jira_account_id exists.")
    if "sg_jira_account_id" not in sg.schema_field_read("HumanUser"):
        print("Creating HumanUser.sg_jira_account_id.")
        sg.schema_field_create("HumanUser", "text", "Jira Account Id")

    print("Locating JIRA project %s" % project_key)
    project = jira.project(project_key)

    print("Retrieving all Shotgun users")
    users = sg.find(
        "HumanUser",
        # User's without email or with TBD (test users) should not be considered.
        [["email", "is_not", None], ["email", "is_not", "TBD"]],
        ["email", "login", "sg_jira_account_id"],
        # We sort by user id so that we always assign users in a deterministic fashion.
        # That is important because the script can be run multiple times over time
        # as a company hires more and more people.
        order=[{"field_name": "id", "direction": "asc"}]
    )
    # Track which emails have already been mapped. This needs to happen first because
    # the same email can be used for multiple users. So if an email has been mapped
    # to account id, we'll skip all users.
    visited_emails = {
        user["email"] for user in users if user["sg_jira_account_id"] is not None
    }

    for user in users:
        # User has already been seen, so skipping it.
        if user["email"] in visited_emails:
            print("The email '{}' from '{}' has already been associated with a JIRA account.".format(user["email"], user["login"]))
            continue

        jira_user = jira.find_jira_assignee_for_issue(
            user["email"],
            jira_project=project
        )
        if jira_user is None:
            print("No user in JIRA was found with the email '{}' from Shotgun user '{}'.".format(user["email"], user["login"]))
            continue

        #print("Associating Shotgun's {0} to JIRA's {1}".format(user["login"], jira_user.name.decode("utf8")))
        sg.update(
            "HumanUser",
            user["id"],
            {"sg_jira_account_id": jira_user.accountId}
        )
        print("Shotgun user '{}' ('{}') has been matched to a JIRA user with the same email.".format(user["login"], user["email"]))
        visited_emails.add(user["email"])


def main():
    parser = argparse.ArgumentParser(
        description="Matches Shotgun users with JIRA users for JIRA Cloud.",
        epilog=(
            "This script will match the first Shotgun user with a given email with the "
            "associated JIRA user. If for some reason there are multiple Shotgun users "
            "with the same email, you can go back in Shotgun and reassign the sg_jira_account_id "
            "value to the right user."
        )
    )
    parser.add_argument(
        "--settings",
        help="Full path to settings file.",
        required=True
    )

    parser.add_argument(
        "--project",
        type=str,
        help="The name of any Jira project that will be synced with Shotgun."
    )
    args = parser.parse_args()

    logger_settings, shotgun_settings, jira_settings, _ = Bridge.read_settings(args.settings)

    if logger_settings:
        logging.config.dictConfig(logger_settings)

    sg = Shotgun(
        shotgun_settings["site"],
        script_name=shotgun_settings["script_name"],
        api_key=shotgun_settings["script_key"]
    )
    jira = JiraSession(
        jira_settings["site"],
        basic_auth=(jira_settings["user"], jira_settings["secret"])
    )

    if "accountId" not in jira.myself():
        print("This script can be run for JIRA Cloud only.")
        return

    sync_jira_users_into_shotgun(sg, jira, args.project)


if __name__ == "__main__":
    main()