# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import mock_jira
from sg_jira.constants import SHOTGUN_JIRA_ID_FIELD

#
# Mock up some Flow Production Tracking that could be used in the different test files
#

SG_USER = {
    "id": 1,
    "type": "HumanUser",
    "login": "ford.prefect",
    "email": mock_jira.JIRA_USER["emailAddress"],
    "name": "Ford Prefect",
    "sg_jira_account_id": mock_jira.JIRA_USER["accountId"],
}

SG_PROJECT = {
    "id": 1,
    "type": "Project",
    "name": "Sync",
    SHOTGUN_JIRA_ID_FIELD: mock_jira.JIRA_PROJECT_KEY,
}

SG_ASSET = {
    "type": "Asset",
    "id": 1,
    "code": "Asset 1",
    "project": SG_PROJECT,
}

SG_TASK = {
    "type": "Task",
    "id": 1,
    "content": "Task 1",
    "project": SG_PROJECT,
    "task_assignees": [SG_USER],
    "description": "Task Description",
}

SG_RETIRED_TASK = {
    "type": "Task",
    "id": 2,
    "content": "Task 2",
    "project": SG_PROJECT,
    "task_assignees": [SG_USER],
    "description": "Task Description",
    "__retired": True,
}
