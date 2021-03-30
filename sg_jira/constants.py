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
    SYNC_SETTINGS_KEY,
]

# Names of the Jira custom fields used to store a reference to a linked Shotgun
# Entity.
JIRA_SHOTGUN_TYPE_FIELD = "SG Type"
JIRA_SHOTGUN_ID_FIELD = "SG Id"
JIRA_SHOTGUN_URL_FIELD = "SG Url"
# Names of the Shotgun custom fields used to store a reference to a linked Jira
# Entity.
SHOTGUN_JIRA_ID_FIELD = "sg_jira_key"

# A Shotgun File/Link field to a link to the synced issue in Jira.
SHOTGUN_JIRA_URL_FIELD = "sg_jira_url"

# A Shotgun check box field used to specify which entities should be synced.
SHOTGUN_SYNC_IN_JIRA_FIELD = "sg_sync_in_jira"

# Shotgun fields handling multiple values
SHOTGUN_LIST_FIELDS = ["multi_entity"]

# Note: this was taken from tk-core with the Tag and Ticket additions
# A dictionary for Shotgun entities which do not store their name
# in the standard "code" field.
SG_ENTITY_SPECIAL_NAME_FIELDS = {
    "Project": "name",
    "Task": "content",
    "HumanUser": "name",
    "Note": "subject",
    "Department": "name",
    "Delivery": "title",
    "Tag": "name",
    "Ticket": "title",
    "ApiUser": "name",
}

# Jira search methods use some paging
# this is the max number of results to get per "page".
JIRA_RESULT_PAGING = 2000
