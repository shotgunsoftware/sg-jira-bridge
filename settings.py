# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
"""
Flow Production Tracking Jira sync settings
"""
import os
import sys
import logging

# Documentation for these settings are available at
# https://developer.shotgridsoftware.com/sg-jira-bridge/settings.html

# Allow users to define their sensitive data in a .env file and
# load it in environment variables with python-dotenv.
# https://pypi.org/project/python-dotenv/
from dotenv import load_dotenv

load_dotenv(override=True)

# fmt: off
# Flow Production Tracking site and credentials
SHOTGUN = {
    "site": os.environ.get("SGJIRA_SG_SITE"),
    "script_name": os.environ.get("SGJIRA_SG_SCRIPT_NAME"),
    "script_key": os.environ.get("SGJIRA_SG_SCRIPT_KEY"),
    "http_proxy": None,  # If set, the Flow Production Tracking connection is done through this proxy.
}
# Jira site and credentials, the user name needs to be an email address or
# the user login name, e.g. ford_escort for "Ford Escort".
JIRA = {
    "site": os.environ.get("SGJIRA_JIRA_SITE"),
    "user": os.environ.get("SGJIRA_JIRA_USER"),
    "secret": os.environ.get("SGJIRA_JIRA_USER_SECRET"),
}

# Define logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    # Settings for the parent of all loggers
    "root": {
        # Set default logging level for all loggers and add the console and
        # file handlers
        "level": "DEBUG",
        "handlers": [
            "console", "file"
        ],
    },
    "loggers": {
        # Set web server level to WARNING so we don't hear about every request
        # If you want to see the requests in the logs, set this to INFO.
        "webapp": {
            "level": "DEBUG"
        }
    },
    # Some formatters, mainly as examples
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)s [%(module)s %(process)d %(thread)d] %(message)s"
        },
        "standard": {
            "format": "%(asctime)s %(levelname)s [%(module)s] %(message)s"
        },
        "simple": {
            "format": "%(levelname)s:%(name)s:%(message)s"
        },
    },
    # Define the logging handlers
    "handlers": {
        # Print out any message to stdout
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "standard"
        },
        "file": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            # this location should be updated to where you store logs
            "filename": "/tmp/sg_jira.log",
            "maxBytes": 1024 * 1024,
            "backupCount": 5
        },
    },
}
# Sync settings. Keys are settings name.

# Add the examples folder to the Python path so the syncers can be loaded.
# Additional paths can be added for custom syncers
sys.path.append(os.path.abspath("./examples"))

SYNC = {
    "default": {
        # The syncer class to use
        "syncer": "sg_jira.TaskIssueSyncer",
        # And its specific settings which are passed to its __init__ method
        "settings": {
            "issue_type": "Task"
        },
    },
    "asset_hierarchy": {
        # The syncer class to use
        "syncer": "asset_hierarchy.AssetHierarchySyncer",
        # And its specific settings which are passed to its __init__ method
        "settings": {
            "asset_issue_type": "Story",
            "task_issue_type": "Task",
        },
    },
    "timelog": {
        # The syncer class to use
        "syncer": "timelog_worklog.TimelogWorklogSyncer",
        # And its specific settings which are passed to its __init__ method
        "settings": {
            "issue_type": "Task",
            # If True, when a worklog is deleted in Jira it will also be deleted in Flow Production Tracking
            "sync_sg_timelog_deletion": True,
            # If True, when a timelog is deleted in Flow Production Tracking, it will also be deleted in Jira
            "sync_jira_worklog_deletion": True,
        },
    },
    "test": {
        # Example of a custom syncer with an additional parameter to define
        # a log level.
        "syncer": "example_sync.ExampleSync",
        "settings": {
            "log_level": logging.DEBUG
        },
    },
    "entities": {
        "syncer": "entities_sync.EntitiesSyncer",
        # "hook": "/Users/darkshot/Work/__TMP/another_folder/hook.py",
        "settings": {
            "entity_mapping": [
                {
                    "sg_entity": "Task",
                    "jira_issue_type": "Task",
                    "field_mapping": [
                        {
                            "sg_field": "content",
                            "jira_field": "summary",
                        },
                        {
                            "sg_field": "sg_description",
                            "jira_field": "description",
                        },
                        {
                            "sg_field": "task_assignees",
                            "jira_field": "assignee",
                        },
                        {
                            "sg_field": "tags",
                            "jira_field": "labels",
                        },
                        {
                            "sg_field": "created_by",
                            "jira_field": "reporter",
                        },
                        {
                            "sg_field": "due_date",
                            "jira_field": "duedate",
                        },
                        {
                            "sg_field": "est_in_mins",
                            "jira_field": "timetracking",
                        },
                        {
                            "sg_field": "addressings_cc",
                            "jira_field": "watches",
                        },
                    ],
                    "status_mapping": {
                        "sync_direction": "jira_to_sg",
                        "sg_field": "sg_status_list",
                        "mapping": {
                            "wtg": "To Do",
                            "rdy": "Open",
                            "ip": "In Progress",
                            "fin": "Done",
                            "hld": "Backlog",
                            "omt": "Closed",
                        }
                    }
                },
                {
                    "sg_entity": "Note",    # Note is a special entity, we only need to add the "sg_entity" key if we want to sync the changes
                    "sync_deletion_direction": "jira_to_sg",
                },
                {
                    "sg_entity": "TimeLog",
                    "sync_deletion_direction": "both_way",
                    "field_mapping": [
                        {
                            "sg_field": "date",
                            "jira_field": "started",
                        },
                        {
                            "sg_field": "duration",
                            "jira_field": "timeSpentSeconds",
                        },
                        {
                            "sg_field": "description",
                            "jira_field": "comment",
                        },
                    ]
                }
            ],
        },
    },
}
# fmt: on
