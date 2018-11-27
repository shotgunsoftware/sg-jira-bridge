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

try:
    # Allow users to define their sensible data in a .env file and
    # load them in environment variables with python-dotenv.
    # https://pypi.org/project/python-dotenv/
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

# Shotgun site and credentials
SHOTGUN = {
    "site": os.environ.get("SG_JIRA_SG_SITE"),
    "script_name": os.environ.get("SG_JIRA_SG_SCRIPT_NAME"),
    "script_key": os.environ.get("SG_JIRA_SG_SCRIPT_KEY"),
}
# Jira site and credentials, the user name needs to be an email address or
# the user login name, e.g. ford_escort for "Ford Escort".
JIRA = {
    "site": os.environ.get("SG_JIRA_JIRA_SITE"),
    "user": os.environ.get("SG_JIRA_JIRA_USER"),
    "secret": os.environ.get("SG_JIRA_JIRA_USER_SECRET"),
}

# Define logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    # Settings for the parent of all loggers
    "root": {
        # Set default logging level for all loggers and add the console and
        # file handlers
        "level": "INFO",
        "handlers": [
            "console", "file"
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
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "simple",
            "filename": "/tmp/sg_jira.log",
            "maxBytes": 1024,
            "backupCount": 5
        },
    },
}
# Sync settings. Keys are settings name.
SYNC = {
    "default": {
        "foo": "blah",
    },
    "test": {

    }
}
