# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

# Settings keys
LOGGING_SETTINGS_KEY = "LOGGING"
SHOTGUN_SETTINGS_KEY = "SHOTGUN"
JIRA_SETTINGS_KEY = "JIRA"
SYNC_SETTINGS_KEY = "SYNC"

# List of all the keys we retrieve from settings
ALL_SETTINGS_KEYS = [
    LOGGING_SETTINGS_KEY,
    SHOTGUN_SETTINGS_KEY,
    JIRA_SETTINGS_KEY,
    SYNC_SETTINGS_KEY
]

# Names of the Jira custom fields used to store a referencen to a linked Shotgun
# Entity.
JIRA_SHOTGUN_TYPE_FIELD = "Shotgun Type"
JIRA_SHOTGUN_ID_FIELD = "Shotgun Id"
# Names of the Shotgun custom fields used to store a reference to a linked Jira
# Entity.
SHOTGUN_JIRA_TYPE_FIELD = "sg_jira_type"
SHOTGUN_JIRA_ID_FIELD = "sg_jira_key"
