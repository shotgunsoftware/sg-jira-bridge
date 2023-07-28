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
JIRA_SHOTGUN_TYPE_FIELD = "Shotgun Type"
JIRA_SHOTGUN_ID_FIELD = "Shotgun Id"
JIRA_SHOTGUN_URL_FIELD = "Shotgun Url"
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

# Mappings

# Define the mapping between Shotgun Task fields and Jira Issue fields
# if the Jira target is None, it means the target field is not settable
# directly.
TASK_FIELDS_MAPPING = {
    "content": "summary",
    "sg_description": "description",
    "sg_status_list": None,
    "task_assignees": "assignee",
    "tags": "labels",
    "created_by": "reporter",
    "due_date": "duedate",
    "est_in_mins": "timetracking",  # time tracking needs to be enabled in Jira.
    "addressings_cc": None,
}

# Define the mapping between Jira Issue fields and Shotgun Task fields
# if the Shotgun target is None, it means the target field is not settable
# directly.
TASK_ISSUE_FIELDS_MAPPING = {
    "summary": "content",
    "description": "sg_description",
    "status": "sg_status_list",
    "assignee": "task_assignees",
    "labels": "tags",
    "duedate": "due_date",
    "timetracking": "est_in_mins",  # time tracking needs to be enabled in Jira.
    "watches": "addressings_cc",
}

TASK_ISSUE_STATUS_MAPPING = {
    "wtg": "To Do",
    "rdy": "Open",
    "ip": "In Progress",
    "fin": "Done",
    "hld": "Backlog",
    "omt": "Closed",
}

# Define the mapping between Shotgun Note fields and Jira Comment fields.
# If the Jira target is None, it means the target field is not settable
# directly.
NOTE_FIELDS_MAPPING = {
    "subject": None,
    "content": None,
    "user": None,
    "tasks": None,
}

# Define the mapping between Shotgun Asset fields and Jira Issue fields
ASSET_FIELDS_MAPPING = {
    "code": "summary",
    "description": "description",
    "tags": "labels",
    "created_by": "reporter",
    "tasks": None,
    "sg_status_list": "status",
}

# The type of Issue link to use when linking a Task Issue to the Issue
# representing the Asset.
JIRA_PARENT_LINK_TYPE = "relates to"

# Define the mapping between Jira Issue fields and Shotgun Asset fields
# if the Shotgun target is None, it means the target field is not settable
# directly.
ISSUE_FIELDS_MAPPING = {
    "summary": "code",
    "description": "description",
    "status": "sg_status_list",
    "labels": "tags",
}

ASSET_ISSUE_STATUS_MAPPING = {
    "wtg": "To Do",
    "rdy": "Open",
    "ip": "In Progress",
    "fin": "Done",
    "hld": "Backlog",
    "omt": "Closed",
}
