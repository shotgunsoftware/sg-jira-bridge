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

# Shotgun credentials
SHOTGUN_SITE = os.environ.get("SG_JIRA_SG_SITE")
SHOTGUN_SCRIPT_NAME = os.environ.get("SG_JIRA_SG_SCRIPT_NAME")
SHOTGUN_SCRIPT_KEY = os.environ.get("SG_JIRA_SG_SCRIPT_KEY")
# Jira credentials
JIRA_SITE = os.environ.get("SG_JIRA_JIRA_SITE")
JIRA_USER = os.environ.get("SG_JIRA_JIRA_USER")
JIRA_USER_SECRET = os.environ.get("SG_JIRA_JIRA_USER_SECRET")

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
            "class" : "logging.handlers.RotatingFileHandler",
            "formatter": "precise",
            "filename": "/tmp/sg_jira.log",
            "maxBytes": 1024,
            "backupCount": 5
        },
    },
}
