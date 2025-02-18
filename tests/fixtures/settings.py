# -*- coding: utf-8 -*-

# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
"""
Flow Production Tracking Jira sync settings
"""
import copy
import os
import sys
import logging

try:
    # Allow users to define their sensible data in a .env file and
    # load it in environment variables with python-dotenv.
    # https://pypi.org/project/python-dotenv/
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

# Shotgun site and credentials
SHOTGUN = {
    "site": os.environ.get("SGJIRA_SG_SITE") or "https://sg.faked.com",
    "script_name": os.environ.get("SGJIRA_SG_SCRIPT_NAME") or "faked",
    "script_key": os.environ.get("SGJIRA_SG_SCRIPT_KEY") or "xxxxxxx",
}
# Jira site and credentials, the user name needs to be an email address or
# the user login name, e.g. ford_escort for "Ford Escort".
JIRA = {
    "site": os.environ.get("SGJIRA_JIRA_SITE") or "https://jira.faked.com",
    "user": os.environ.get("SGJIRA_JIRA_USER") or "faked",
    "secret": os.environ.get("SGJIRA_JIRA_USER_SECRET") or "xxxxxxx",
}

# Define logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    # Settings for the parent of all loggers
    "root": {
        # Set default logging level for all loggers and add the console handler
        "level": "INFO",
        "handlers": ["console"],
    },
    "loggers": {"sg_jira.syncer": {"level": "DEBUG"}, "sg_jira.jira_session": {"level": "WARNING"}, "sg_jira.shotgun_session": {"level": "WARNING"}, "sg_jira.bridge": {"level": "WARNING"}},
    # Some formatters, mainly as examples
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"
        },
        "simple": {"format": "%(levelname)s:%(name)s:%(message)s"},
    },
    # Define the logging handlers
    "handlers": {
        # Print out any message to stdout
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
}
# Sync settings. Keys are settings name.

# Add the ./ folder to the Python path so test syncers can be loaded by unit tests
sys.path.append(
    os.path.abspath(
        os.path.dirname(__file__),
    )
)

# Add the ../../examples folder to the Python path so example syncers can be loaded by unit tests
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "examples"))
)

SYNC = {
    "task_issue": {
        # The syncer class to use
        "syncer": "sg_jira.TaskIssueSyncer",
        # And its specific settings which are passed to its __init__ method
        "settings": {"foo": "blah"},
    },
    "bad_setup": {
        # A syncer which fails in various stages
        "syncer": "syncers.bad_syncer.BadSyncer",
        "settings": {"fail_on_setup": True},
    },
    "bad_sg_accept": {
        # A syncer which fails in various stages
        "syncer": "syncers.bad_syncer.BadSyncer",
        "settings": {"fail_on_sg_accept": True},
    },
    "bad_sg_sync": {
        # A syncer which fails in various stages
        "syncer": "syncers.bad_syncer.BadSyncer",
        "settings": {"fail_on_sg_sync": True},
    },
    "example": {
        # Example of a custom syncer with an additional parameter to define
        # a log level.
        "syncer": "example_sync.ExampleSync",
        "settings": {"log_level": logging.DEBUG},
    },
    "asset_hierarchy": {
        # The syncer class to use
        "syncer": "asset_hierarchy.AssetHierarchySyncer",
        # And its specific settings which are passed to its __init__ method
        "settings": {"asset_issue_type": "Story", "task_issue_type": "Task"},
    },
    "unicode_😀": {
        # The syncer class to use
        "syncer": "sg_jira.TaskIssueSyncer",
        # And its specific settings which are passed to its __init__ method
        "settings": {"foo_îéö😀": "blah_îéö😀"},
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
    "timelog_no_deletion": {
        # The syncer class to use
        "syncer": "timelog_worklog.TimelogWorklogSyncer",
        # And its specific settings which are passed to its __init__ method
        "settings": {
            "issue_type": "Task",
            # If True, when a worklog is deleted in Jira it will also be deleted in Flow Production Tracking
            "sync_sg_timelog_deletion": False,
            # If True, when a timelog is deleted in Flow Production Tracking, it will also be deleted in Jira
            "sync_jira_worklog_deletion": False,
        },
    },
    "entities_generic": {
        "syncer": "sg_jira.EntitiesGenericSyncer",
        "settings": {
            "entity_mapping": [
                {
                    "sg_entity": "Task",
                    "jira_issue_type": "Task",
                    "field_mapping": [
                        {
                            "sg_field": "content",
                            "jira_field": "summary"
                        },
                        {
                            "sg_field": "sg_description",
                            "jira_field": "description"
                        },
                    ],
                    "status_mapping": {
                        "sg_field": "sg_status_list",
                        "mapping": {
                            "wtg": "To Do",
                        }
                    }
                },
                {
                    "sg_entity": "Note",
                },
                {
                    "sg_entity": "TimeLog",
                    "field_mapping": [
                        {
                            "sg_field": "description",
                            "jira_field": "comment",
                        },
                        {
                            "sg_field": "duration",
                            "jira_field": "timeSpentSeconds",
                        }
                    ]
                }
            ]
        }
    }
}


# Extra settings for testing all the entities generic syncer use cases
SYNC["entities_generic_bad_sg_entity_formatting"] = copy.deepcopy(SYNC["entities_generic"])
del SYNC["entities_generic_bad_sg_entity_formatting"]["settings"]["entity_mapping"][0]["sg_entity"]

SYNC["entities_generic_bad_jira_issue_type_formatting"] = copy.deepcopy(SYNC["entities_generic"])
del SYNC["entities_generic_bad_jira_issue_type_formatting"]["settings"]["entity_mapping"][0]["jira_issue_type"]

SYNC["entities_generic_bad_fields_formatting"] = copy.deepcopy(SYNC["entities_generic"])
del SYNC["entities_generic_bad_fields_formatting"]["settings"]["entity_mapping"][0]["field_mapping"]

SYNC["entities_generic_bad_fields_formatting_missing_sg_field_key"] = copy.deepcopy(SYNC["entities_generic"])
del SYNC["entities_generic_bad_fields_formatting_missing_sg_field_key"]["settings"]["entity_mapping"][0]["field_mapping"][0]["sg_field"]

SYNC["entities_generic_bad_fields_formatting_missing_jira_field_key"] = copy.deepcopy(SYNC["entities_generic"])
del SYNC["entities_generic_bad_fields_formatting_missing_jira_field_key"]["settings"]["entity_mapping"][0]["field_mapping"][0]["jira_field"]

SYNC["entities_generic_bad_status_formatting_missing_sg_field_key"] = copy.deepcopy(SYNC["entities_generic"])
del SYNC["entities_generic_bad_status_formatting_missing_sg_field_key"]["settings"]["entity_mapping"][0]["status_mapping"]["sg_field"]

SYNC["entities_generic_bad_status_formatting_missing_mapping_key"] = copy.deepcopy(SYNC["entities_generic"])
del SYNC["entities_generic_bad_status_formatting_missing_mapping_key"]["settings"]["entity_mapping"][0]["status_mapping"]["mapping"]

SYNC["entities_generic_jira_to_sg"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_jira_to_sg"]["settings"]["entity_mapping"][0]["sync_direction"] = "jira_to_sg"

SYNC["entities_generic_sg_to_jira"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_sg_to_jira"]["settings"]["entity_mapping"][0]["sync_direction"] = "sg_to_jira"

SYNC["entities_generic_both_way"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_both_way"]["settings"]["entity_mapping"][0]["sync_direction"] = "both_way"

SYNC["entities_generic_field_directions"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_field_directions"]["settings"]["entity_mapping"][0]["field_mapping"][1]["sync_direction"] = "sg_to_jira"
SYNC["entities_generic_field_directions"]["settings"]["entity_mapping"][0]["field_mapping"].append(
    {
        "sg_field": "due_date",
        "jira_field": "duedate",
        "sync_direction": "jira_to_sg"
    }
)

SYNC["entities_generic_status_both_way"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_status_both_way"]["settings"]["entity_mapping"][0]["status_mapping"]["sync_direction"] = "both_way"

SYNC["entities_generic_status_sg_to_jira"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_status_sg_to_jira"]["settings"]["entity_mapping"][0]["status_mapping"]["sync_direction"] = "sg_to_jira"

SYNC["entities_generic_status_jira_to_sg"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_status_jira_to_sg"]["settings"]["entity_mapping"][0]["status_mapping"]["sync_direction"] = "jira_to_sg"

SYNC["entities_generic_both_way_deletion"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_both_way_deletion"]["settings"]["entity_mapping"][1]["sync_deletion_direction"] = "both_way"
SYNC["entities_generic_both_way_deletion"]["settings"]["entity_mapping"][2]["sync_deletion_direction"] = "both_way"

SYNC["entities_generic_sg_to_jira_deletion"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_sg_to_jira_deletion"]["settings"]["entity_mapping"][1]["sync_deletion_direction"] = "sg_to_jira"
SYNC["entities_generic_sg_to_jira_deletion"]["settings"]["entity_mapping"][2]["sync_deletion_direction"] = "sg_to_jira"

SYNC["entities_generic_jira_to_sg_deletion"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_jira_to_sg_deletion"]["settings"]["entity_mapping"][1]["sync_deletion_direction"] = "jira_to_sg"
SYNC["entities_generic_jira_to_sg_deletion"]["settings"]["entity_mapping"][2]["sync_deletion_direction"] = "jira_to_sg"

SYNC["entities_generic_bad_jira_issue_type"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_bad_jira_issue_type"]["settings"]["entity_mapping"][0]["jira_issue_type"] = "Unknown Issue Type"

SYNC["entities_generic_bad_assignee_field_type"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_bad_assignee_field_type"]["settings"]["entity_mapping"][0]["field_mapping"].append(
    {
        "jira_field": "assignee",
        "sg_field": "start_date"
    }
)

SYNC["entities_generic_bad_assignee_field_entity_type"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_bad_assignee_field_entity_type"]["settings"]["entity_mapping"][0]["field_mapping"].append(
    {
        "jira_field": "assignee",
        "sg_field": "sg_versions"
    }
)

SYNC["entities_generic_with_project"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_with_project"]["settings"]["entity_mapping"].append(
    {
        "sg_entity": "Project",
        "sg_fields": []
    }
)

SYNC["entities_generic_sg_entity_with_missing_field_in_schema"] = copy.deepcopy(SYNC["entities_generic"])
SYNC["entities_generic_sg_entity_with_missing_field_in_schema"]["settings"]["entity_mapping"].append(
    {
        "sg_entity": "Asset",
        "sg_fields": []
    }
)