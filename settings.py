# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
"""
Shotgun Jira sync settings
"""
import os
import sys
import logging

# Documentation for these settings are available at 
# https://developer.shotgunsoftware.com/sg-jira-bridge/settings.html

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
    "site": os.environ.get("SGJIRA_SG_SITE"),
    "script_name": os.environ.get("SGJIRA_SG_SCRIPT_NAME"),
    "script_key": os.environ.get("SGJIRA_SG_SCRIPT_KEY"),
    "http_proxy": None,  # If set, the Shotgun connection is done through this proxy.
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
            "level": "WARNING"
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
            "level": "ERROR",
            "class": "logging.StreamHandler",
            "formatter": "standard"
        },
        "file": {
            "level": "INFO",
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
    "test": {
        # Example of a custom syncer with an additional parameter to define
        # a log level.
        "syncer": "example_sync.ExampleSync",
        "settings": {
            "log_level": logging.DEBUG
        },
    }
}
