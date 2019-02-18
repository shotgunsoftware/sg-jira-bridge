# -*- coding: utf-8 -*-

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
        "handlers": [
            "console"
        ],
    },
    # Some formatters, mainly as examples
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"
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
            "formatter": "simple"
        },
    },
}
# Sync settings. Keys are settings name.

# Add the ./ folder to the Python path so test syncers can be loaded by unit tests
sys.path.append(os.path.abspath(
    os.path.dirname(__file__),
))

SYNC = {
    "task_issue": {
        # The syncer class to use
        "syncer": "sg_jira.TaskIssueSyncer",
        # And its specific settings which are passed to its __init__ method
        "settings": {
            "foo": "blah"
        },
    },
    "bad_setup": {
        # A syncer which fails in various stages
        "syncer": "syncers.bad_syncer.BadSyncer",
        "settings": {
            "fail_on_setup": True,
        },
    },
    "bad_sg_accept": {
        # A syncer which fails in various stages
        "syncer": "syncers.bad_syncer.BadSyncer",
        "settings": {
            "fail_on_sg_accept": True,
        },
    },
    "bad_sg_sync": {
        # A syncer which fails in various stages
        "syncer": "syncers.bad_syncer.BadSyncer",
        "settings": {
            "fail_on_sg_sync": True,
        },
    },
    "example": {
        # Example of a custom syncer with an additional parameter to define
        # a log level.
        "syncer": "example_sync.ExampleSync",
        "settings": {
            "log_level": logging.DEBUG
        },
    },
    "unicode_😀": {
        # The syncer class to use
        "syncer": "sg_jira.TaskIssueSyncer",
        # And its specific settings which are passed to its __init__ method
        "settings": {
            "foo_îéö😀": "blah_îéö😀"
        },

    }
}
