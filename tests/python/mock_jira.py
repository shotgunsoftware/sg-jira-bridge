# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import copy
import re

import jira
from jira.resources import Project as JiraProject
from jira.resources import IssueType, Issue, User, Comment, IssueLink, Worklog, Status
from jira import JIRAError

# Faked Jira Project, Issue, change log and event
JIRA_PROJECT_KEY = "UTest"
JIRA_PROJECT = {
    "name": "Tasks unit test",
    "self": "https://mocked.faked.com/rest/api/2/project/10400",
    "projectTypeKey": "software",
    "simplified": False,
    "key": JIRA_PROJECT_KEY,
    "isPrivate": False,
    "id": "12345",
    "expand": "description,lead,issueTypes,url,projectKeys",
}

JIRA_USER = {
    "accountId": "123456:60e119d8-6a49-4375-95b6-6740fc8e75e0",
    "active": True,
    "displayName": "Ford Prefect",
    "emailAddress": "fprefect@weefree.com",
    "key": "ford.prefect1",
    "name": "ford.prefect1",
    "self": "https://myjira.atlassian.net/rest/api/2/user?accountId=123456:60e119d8-6a49-4375-95b6-6740fc8e75e0",
    "timeZone": "Europe/Paris",
}

JIRA_USER_2 = {
    "accountId": "5b6a25ab7c14b729f2208297",
    "active": True,
    "displayName": "Sync Sync",
    "emailAddress": "syncsync.@foo.com",
    "key": "sync-sync",
    "name": "sync-sync",
    "self": "https://myjira.atlassian.net/rest/api/2/user?accountId=12343456778",
    "timeZone": "America/New_York",
}

ISSUE_FIELDS = {
    "assignee": {
        "autoCompleteUrl": "https://mocked.faked.com/rest/api/latest/user/assignable/search?project=ST3&query=",
        "hasDefaultValue": False,
        "key": "assignee",
        "name": "Assignee",
        "operations": ["set"],
        "required": False,
        "schema": {"system": "assignee", "type": "user"},
    },
    "attachment": {
        "hasDefaultValue": False,
        "key": "attachment",
        "name": "Attachment",
        "operations": [],
        "required": False,
        "schema": {"items": "attachment", "system": "attachment", "type": "array"},
    },
    "components": {
        "allowedValues": [],
        "hasDefaultValue": False,
        "key": "components",
        "name": "Component/s",
        "operations": ["add", "set", "remove"],
        "required": False,
        "schema": {"items": "component", "system": "components", "type": "array"},
    },
    "customfield_10003": {
        "hasDefaultValue": False,
        "key": "customfield_10003",
        "name": "Epic Link",
        "operations": ["set"],
        "required": False,
        "schema": {
            "custom": "com.pyxis.greenhopper.jira:gh-epic-link",
            "customId": 10003,
            "type": "any",
        },
    },
    "customfield_11501": {
        "hasDefaultValue": False,
        "key": "customfield_11501",
        "name": "Shotgun ID",
        "operations": ["set"],
        "required": False,
        "schema": {
            "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
            "customId": 11501,
            "type": "string",
        },
    },
    "customfield_11502": {
        "hasDefaultValue": False,
        "key": "customfield_11502",
        "name": "Shotgun Type",
        "operations": ["set"],
        "required": False,
        "schema": {
            "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
            "customId": 11502,
            "type": "string",
        },
    },
    "customfield_11503": {
        "hasDefaultValue": False,
        "key": "customfield_11503",
        "name": "Shotgun URL",
        "operations": ["set"],
        "required": False,
        "schema": {
            "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
            "customId": 11503,
            "type": "string",
        },
    },
    "customfield_11504": {
        "hasDefaultValue": False,
        "key": "customfield_11504",
        "name": "Sync in FPTR",
        "operations": ["set"],
        "required": False,
        "schema": {
            "custom": "com.atlassian.jira.plugin.system.customfieldtypes:select",
            "customId": 11504,
            "type": "option",
        },
    },
    "description": {
        "hasDefaultValue": False,
        "key": "description",
        "name": "Description",
        "operations": ["set"],
        "required": False,
        "schema": {"system": "description", "type": "string"},
    },
    "fixVersions": {
        "allowedValues": [],
        "hasDefaultValue": False,
        "key": "fixVersions",
        "name": "Fix Version/s",
        "operations": ["set", "add", "remove"],
        "required": False,
        "schema": {"items": "version", "system": "fixVersions", "type": "array"},
    },
    "issuelinks": {
        "autoCompleteUrl": "https://mocked.faked.com/rest/api/2/issue/picker?currentProjectId=&showSubTaskParent=true&showSubTasks=true&currentIssueKey=null&query=",
        "hasDefaultValue": False,
        "key": "issuelinks",
        "name": "Linked Issues",
        "operations": ["add"],
        "required": False,
        "schema": {"items": "issuelinks", "system": "issuelinks", "type": "array"},
    },
    "issuetype": {
        "allowedValues": [
            {
                "avatarId": 10318,
                "description": "A task that needs to be done.",
                "iconUrl": "https://mocked.faked.com/secure/viewavatar?size=xsmall&avatarId=10318&avatarType=issuetype",
                "id": "10000",
                "name": "Task",
                "self": "https://mocked.faked.com/rest/api/2/issuetype/10000",
                "subtask": False,
            }
        ],
        "hasDefaultValue": False,
        "key": "issuetype",
        "name": "Issue Type",
        "operations": [],
        "required": True,
        "schema": {"system": "issuetype", "type": "issuetype"},
    },
    "labels": {
        "autoCompleteUrl": "https://mocked.faked.com/rest/api/1.0/labels/suggest?query=",
        "hasDefaultValue": False,
        "key": "labels",
        "name": "Labels",
        "operations": ["add", "set", "remove"],
        "required": False,
        "schema": {"items": "string", "system": "labels", "type": "array"},
    },
    "parent": {
        "required": False,
        "schema": {'system': 'parent', 'type': 'issuelink'},
        "name": "Parent",
        "key": "parent",
        "hasDefaultValue": False,
        "operations": ["set"],
    },
    "priority": {
        "allowedValues": [
            {
                "iconUrl": "https://mocked.faked.com/images/icons/priorities/highest.svg",
                "id": "1",
                "name": "Highest",
                "self": "https://mocked.faked.com/rest/api/2/priority/1",
            },
            {
                "iconUrl": "https://mocked.faked.com/images/icons/priorities/high.svg",
                "id": "2",
                "name": "High",
                "self": "https://mocked.faked.com/rest/api/2/priority/2",
            },
            {
                "iconUrl": "https://mocked.faked.com/images/icons/priorities/medium.svg",
                "id": "3",
                "name": "Medium",
                "self": "https://mocked.faked.com/rest/api/2/priority/3",
            },
            {
                "iconUrl": "https://mocked.faked.com/images/icons/priorities/low.svg",
                "id": "4",
                "name": "Low",
                "self": "https://mocked.faked.com/rest/api/2/priority/4",
            },
            {
                "iconUrl": "https://mocked.faked.com/images/icons/priorities/lowest.svg",
                "id": "5",
                "name": "Lowest",
                "self": "https://mocked.faked.com/rest/api/2/priority/5",
            },
        ],
        "defaultValue": {
            "iconUrl": "https://mocked.faked.com/images/icons/priorities/medium.svg",
            "id": "3",
            "name": "Medium",
            "self": "https://mocked.faked.com/rest/api/2/priority/3",
        },
        "hasDefaultValue": True,
        "key": "priority",
        "name": "Priority",
        "operations": ["set"],
        "required": True,
        "schema": {"system": "priority", "type": "priority"},
    },
    "project": {
        "allowedValues": [
            {
                "avatarUrls": {
                    "16x16": "https://mocked.faked.com/secure/projectavatar?size=xsmall&avatarId=10324",
                    "24x24": "https://mocked.faked.com/secure/projectavatar?size=small&avatarId=10324",
                    "32x32": "https://mocked.faked.com/secure/projectavatar?size=medium&avatarId=10324",
                    "48x48": "https://mocked.faked.com/secure/projectavatar?avatarId=10324",
                },
                "id": "11112",
                "key": "ST3",
                "name": "Steph Tests 3",
                "projectTypeKey": "software",
                "self": "https://mocked.faked.com/rest/api/2/project/11112",
            }
        ],
        "hasDefaultValue": False,
        "key": "project",
        "name": "Project",
        "operations": ["set"],
        "required": True,
        "schema": {"system": "project", "type": "project"},
    },
    "reporter": {
        "autoCompleteUrl": "https://mocked.faked.com/rest/api/latest/user/search?query=",
        "hasDefaultValue": True,
        "key": "reporter",
        "name": "Reporter",
        "operations": ["set"],
        "required": False,
        "schema": {"system": "reporter", "type": "user"},
    },
    "summary": {
        "hasDefaultValue": False,
        "key": "summary",
        "name": "Summary",
        "operations": ["set"],
        "required": True,
        "schema": {"system": "summary", "type": "string"},
    },
}

TASK_CREATE_META = {
    "description": "A task that needs to be done.",
    "expand": "fields",
    "fields": ISSUE_FIELDS,
    "iconUrl": "https://mocked.faked.com/secure/viewavatar?size=xsmall&avatarId=10318&avatarType=issuetype",
    "id": "10000",
    "name": "Task",
    "self": "https://mocked.faked.com/rest/api/2/issuetype/10000",
    "subtask": False,
}

TASK_EDIT_META = {"fields": ISSUE_FIELDS}

ISSUE_BASE_RAW = {
    "expand": "renderedFields,names,schema,operations,editmeta,changelog,versionedRepresentations",
    "fields": {
        "assignee": JIRA_USER,
        "attachment": [],
        "components": [],
        "created": "2018-12-18T06:15:05.626-0500",
        "creator": {
            "accountId": "123456%3Aaecf5cfd-e13d-abcdef",
            "active": True,
            "displayName": "Sync Sync",
            "emailAddress": "syncsync@blah.com",
            "key": "syncsync",
            "name": "syncsync",
            "self": "https://myjira.atlassian.net/rest/api/2/user?accountId=123456%3Aaecf5cfd-e13d-abcdef",
            "timeZone": "America/New_York",
        },
        "customfield_11501": "11794",
        "customfield_11502": "Task",
        "description": "Task (11794)",
        "duedate": None,
        "environment": None,
        "fixVersions": [],
        "issuelinks": [],
        "issuetype": {
            "avatarId": 10318,
            "description": "A task that needs to be done.",
            "iconUrl": "https://myjira.atlassian.net/secure/viewavatar?size=xsmall&avatarId=10318&avatarType=issuetype",
            "id": "10000",
            "name": "Task",
            "self": "https://myjira.atlassian.net/rest/api/2/issuetype/10000",
            "subtask": False,
        },
        "labels": [],
        "lastViewed": "2018-12-18T09:44:27.653-0500",
        "priority": {
            "iconUrl": "https://myjira.atlassian.net/images/icons/priorities/medium.svg",
            "id": "3",
            "name": "Medium",
            "self": "https://myjira.atlassian.net/rest/api/2/priority/3",
        },
        "project": JIRA_PROJECT,
        "reporter": {
            "accountId": "12343456778",
            "active": True,
            "displayName": "Sync Sync",
            "emailAddress": "syncsync.@foo.com",
            "key": "sync-sync",
            "name": "sync-sync",
            "self": "https://myjira.atlassian.net/rest/api/2/user?accountId=12343456778",
            "timeZone": "America/New_York",
        },
        "resolution": None,
        "resolutiondate": None,
        "security": None,
        "status": {
            "description": "",
            "iconUrl": "https://myjira.atlassian.net/",
            "id": "10204",
            "name": "Backlog",
            "self": "https://myjira.atlassian.net/rest/api/2/status/10204",
            "statusCategory": {
                "colorName": "blue-gray",
                "id": 2,
                "key": "new",
                "name": "New",
                "self": "https://myjira.atlassian.net/rest/api/2/statuscategory/2",
            },
        },
        "subtasks": [],
        "summary": "foo bar",
        "updated": "2018-12-18T09:44:27.572-0500",
        "versions": [],
        "votes": {
            "hasVoted": False,
            "self": "https://myjira.atlassian.net/rest/api/2/issue/ST3-4/votes",
            "votes": 0,
        },
        "watches": {
            "isWatching": False,
            "self": "https://myjira.atlassian.net/rest/api/2/issue/ST3-4/watchers",
            "watchCount": 1,
        },
        "workratio": -1,
    },
}

RESOURCE_OPTIONS = {
    "rest_api_version": "2",
    "agile_rest_api_version": "1.0",
    "verify": True,
    "context_path": "/",
    "agile_rest_path": "greenhopper",
    "server": "https://myjira.atlassian.net",
    "check_update": False,
    "headers": {
        "Content-Type": "application/json",
        "X-Atlassian-Token": "no-check",
        "Cache-Control": "no-cache",
    },
    "auth_url": "/rest/auth/1/session",
    "async_workers": 5,
    "resilient": True,
    "async": False,
    "client_cert": None,
    "rest_path": "api",
}

ISSUE_CREATED_PAYLOAD = {
    "webhookEvent": "jira:issue_created",
    "changelog": {
        "items": {}
    },
    "issue": {
        "id": "FAKED-01"
    }
}

ISSUE_UPDATED_PAYLOAD = {
    "webhookEvent": "jira:issue_updated",
    "changelog": {
        "items": [
            {
                "field": "description",
                "fieldId": "description",
            },
        ]
    },
    "issue": {
        "id": "FAKED-01"
    }
}

WORKLOG_PAYLOAD = {
    "webhookEvent": "worklog_deleted",
    "worklog": {
        "id": "100001",
        "issueId": "FAKED-01",
        "author": {
            "accountId": JIRA_USER_2["accountId"],
        },
        "updateAuthor": {
            "accountId": JIRA_USER_2["accountId"],
        },
    }
}


class MockedSession(object):
    def put(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return {}


class MockedIssue(Issue):
    def __init__(self, *args, **kwargs):
        super(MockedIssue, self).__init__(*args, **kwargs)
        self._worklogs = []
        self._comments = []

    def update(self, fields, *args, **kwargs):
        raw = self.raw
        raw["fields"].update(fields)
        self._parse_raw(raw)


class MockedComment(Comment):
    def update(self, *args, **kwargs):
        raw = self.raw
        for k in kwargs:
            raw[k] = kwargs[k]
        self._parse_raw(raw)

    def delete(self, *args, **kwargs):
        """Mocked Jira method to delete a comment"""
        self.issue._comments.remove(self)

class MockedWorklog(Worklog):
    def update(self, *args, **kwargs):
        """Mocked Jira method to update a worklog"""
        raw = self.raw
        for k in kwargs:
            if k == "fields":
                for v in kwargs[k]:
                    raw[v] = kwargs[k][v]
            raw[k] = kwargs[k]
        self._parse_raw(raw)

    def delete(self, *args, **kwargs):
        """Mocked Jira method to delete a worklog"""
        self.issue._worklogs.remove(self)


class MockedJira(object):
    """
    A class to mock a Jira connection and methods used by the bridge.
    """

    def __init__(self, *args, **kwargs):
        self._projects = []
        self._createmeta = {}
        self._issues = {}
        self._issue_links = []

    def set_projects(self, projects):
        """
        Set the list of projects to the given list.

        :param projects: A list of project dictionaries:

        :Example:

        mocked_jira.set_projects([{
            "name": "Tasks unit test",
            "self": "https://mocked.faked.com/rest/api/2/project/10400",
            "projectTypeKey": "software",
            "simplified": False,
            "key": JIRA_PROJECT_KEY,
            "isPrivate": False,
            "id": "12345",
            "expand": "description,lead,issueTypes,url,projectKeys"
        }])
        """
        self._projects = []
        for project in projects:
            self._projects.append(JiraProject(None, None, raw=project))

    def projects(self):
        """
        Mocked Jira method.
        Return a list of :class:`JiraProject`.
        """
        return self._projects

    def project(self, project_id):
        """
        Mocked Jira method
        Return a :class:`JiraProject`
        """
        for project in self._projects:
            if project.key == project_id:
                return project
        raise JIRAError("Unable to find resource Project({})".format(project_id))

    def createmeta_issuetypes(self, *args):
        """
        Mocked Jira method.
        Return a dictionary with create metadata for all projects.
        """
        return {"values": [{"fields": ISSUE_FIELDS}]}

    def createmeta(self, *args, **kwargs):
        """
        Mocked Jira method.
        Return a dictionary with create metadata for all projects.
        """
        projects_meta = []
        for project in self._projects:
            projects_meta.append(
                {
                    "key": project.key,
                    "name": project.name,
                    "self": "https://mocked.faked.com/rest/api/2/project/%s"
                    % project.id,
                    "expand": "issuetypes",
                    "id": project.id,
                    "issuetypes": [TASK_CREATE_META],
                }
            )

        return {
            "expand": "projects",
            "projects": projects_meta,
        }

    def editmeta(self, issue):
        """
        Mocked Jira method.
        Return a dictionary with edit metadata for the given issue.
        """
        return TASK_EDIT_META

    def issue_type_by_name(self, name, project=None):
        """
        Mocked Jira method.
        Return a :class:`IssueType`.
        """
        return IssueType(None, None, raw={"name": name, "id": 12345})

    def current_user(self):
        """
        Mocked Jira method.
        Return a string.
        """
        return "ford.prefect1"

    def myself(self):
        """
        Mocked Jira method.
        Return a dictionary of the fields for the current user.
        """
        return JIRA_USER

    def fields(self):
        """
        Mocked Jira method.
        Return a list of dictionaries.
        """
        return [
            {
                "name": "Issue Type",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "issuetype",
                "clauseNames": ["issuetype", "type"],
                "orderable": True,
                "id": "issuetype",
                "schema": {"type": "issuetype", "system": "issuetype"},
            },
            {
                "name": "Project",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "project",
                "clauseNames": ["project"],
                "orderable": False,
                "id": "project",
                "schema": {"type": "project", "system": "project"},
            },
            {
                "name": "test extra text",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11000",
                "clauseNames": ["cf[11000]", "test extra text"],
                "orderable": True,
                "id": "customfield_11000",
                "schema": {
                    "customId": 11000,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                },
            },
            {
                "name": "Fix Version/s",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "fixVersions",
                "clauseNames": ["fixVersion"],
                "orderable": True,
                "id": "fixVersions",
                "schema": {
                    "items": "version",
                    "type": "array",
                    "system": "fixVersions",
                },
            },
            {
                "name": "Resolution",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "resolution",
                "clauseNames": ["resolution"],
                "orderable": True,
                "id": "resolution",
                "schema": {"type": "resolution", "system": "resolution"},
            },
            {
                "name": "Implementation Details",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11400",
                "clauseNames": ["cf[11400]", "Implementation Details"],
                "orderable": True,
                "id": "customfield_11400",
                "schema": {
                    "customId": 11400,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textarea",
                },
            },
            {
                "name": "Parent Link",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10500",
                "clauseNames": ["cf[10500]", "Parent Link"],
                "orderable": True,
                "id": "customfield_10500",
                "schema": {
                    "customId": 10500,
                    "type": "any",
                    "custom": "com.atlassian.jpo:jpo-custom-field-parent",
                },
            },
            {
                "name": "Request Type",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11513",
                "clauseNames": ["cf[11513]", "Request Type"],
                "orderable": True,
                "id": "customfield_11513",
                "schema": {
                    "customId": 11513,
                    "type": "sd-customerrequesttype",
                    "custom": "com.atlassian.servicedesk:vp-origin",
                },
            },
            {
                "name": "Start date",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11512",
                "clauseNames": ["cf[11512]", "Start date"],
                "orderable": True,
                "id": "customfield_11512",
                "schema": {
                    "customId": 11512,
                    "type": "date",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:datepicker",
                },
            },
            {
                "name": "Story point estimate",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11515",
                "clauseNames": ["cf[11515]", "Story point estimate"],
                "orderable": True,
                "id": "customfield_11515",
                "schema": {
                    "customId": 11515,
                    "type": "number",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:float",
                },
            },
            {
                "name": "Team",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10700",
                "clauseNames": ["cf[10700]", "Team"],
                "orderable": True,
                "id": "customfield_10700",
                "schema": {
                    "customId": 10700,
                    "type": "any",
                    "custom": "com.atlassian.teams:rm-teams-custom-field-team",
                },
            },
            {
                "name": "Request participants",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11514",
                "clauseNames": ["cf[11514]", "Request participants"],
                "orderable": True,
                "id": "customfield_11514",
                "schema": {
                    "items": "user",
                    "customId": 11514,
                    "type": "array",
                    "custom": "com.atlassian.servicedesk:sd-request-participants",
                },
            },
            {
                "name": "Level",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10900",
                "clauseNames": ["cf[10900]"],
                "orderable": True,
                "id": "customfield_10900",
                "schema": {
                    "customId": 10900,
                    "type": "option",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:select",
                },
            },
            {
                "name": "Issue color",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11516",
                "clauseNames": ["cf[11516]", "Issue color"],
                "orderable": True,
                "id": "customfield_11516",
                "schema": {
                    "customId": 11516,
                    "type": "string",
                    "custom": "com.pyxis.greenhopper.jira:jsw-issue-color",
                },
            },
            {
                "name": "Resolved",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "resolutiondate",
                "clauseNames": ["resolutiondate", "resolved"],
                "orderable": False,
                "id": "resolutiondate",
                "schema": {"type": "datetime", "system": "resolutiondate"},
            },
            {
                "name": "Work Ratio",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "workratio",
                "clauseNames": ["workratio"],
                "orderable": False,
                "id": "workratio",
                "schema": {"type": "number", "system": "workratio"},
            },
            {
                "name": "Last Viewed",
                "searchable": False,
                "navigable": True,
                "custom": False,
                "key": "lastViewed",
                "clauseNames": ["lastViewed"],
                "orderable": False,
                "id": "lastViewed",
                "schema": {"type": "datetime", "system": "lastViewed"},
            },
            {
                "name": "Watchers",
                "searchable": False,
                "navigable": True,
                "custom": False,
                "key": "watches",
                "clauseNames": ["watchers"],
                "orderable": False,
                "id": "watches",
                "schema": {"type": "watches", "system": "watches"},
            },
            {
                "name": "Images",
                "searchable": False,
                "navigable": True,
                "custom": False,
                "key": "thumbnail",
                "clauseNames": [],
                "orderable": False,
                "id": "thumbnail",
            },
            {
                "name": "Created",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "created",
                "clauseNames": ["created", "createdDate"],
                "orderable": False,
                "id": "created",
                "schema": {"type": "datetime", "system": "created"},
            },
            {
                "name": "Priority",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "priority",
                "clauseNames": ["priority"],
                "orderable": True,
                "id": "priority",
                "schema": {"type": "priority", "system": "priority"},
            },
            {
                "name": "sg_key",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10100",
                "clauseNames": ["cf[10100]", "sg_key"],
                "orderable": True,
                "id": "customfield_10100",
                "schema": {
                    "customId": 10100,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                },
            },
            {
                "name": "test_int",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10101",
                "clauseNames": ["cf[10101]", "test_int"],
                "orderable": True,
                "id": "customfield_10101",
                "schema": {
                    "customId": 10101,
                    "type": "number",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:float",
                },
            },
            {
                "name": "Shotgun Status",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11511",
                "clauseNames": ["cf[11511]", "Shotgun Status"],
                "orderable": True,
                "id": "customfield_11511",
                "schema": {
                    "customId": 11511,
                    "type": "option",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:select",
                },
            },
            {
                "name": "sg_url",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10300",
                "clauseNames": ["cf[10300]", "sg_url"],
                "orderable": True,
                "id": "customfield_10300",
                "schema": {
                    "customId": 10300,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:url",
                },
            },
            {
                "name": "Shotgun TimeLogs",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11517",
                "clauseNames": ["cf[11517]", "Shotgun TimeLogs"],
                "orderable": True,
                "id": "customfield_11517",
                "schema": {
                    "customId": 11517,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textarea",
                },
            },
            {
                "name": "Sync In FPTR",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11504",
                "clauseNames": ["cf[11504]", "Sync In FPTR"],
                "orderable": True,
                "id": "customfield_11504",
                "schema": {
                    "customId": 11504,
                    "type": "option",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:select",
                },
            },
            {
                "name": "Labels",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "labels",
                "clauseNames": ["labels"],
                "orderable": True,
                "id": "labels",
                "schema": {
                    "items": "string",
                    "type": "array",
                    "system": "labels",
                },
            },
            {
                "name": "Fancy Due Date 2",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11510",
                "clauseNames": ["cf[11510]", "Fancy Due Date 2"],
                "orderable": True,
                "id": "customfield_11510",
                "schema": {
                    "customId": 11510,
                    "type": "date",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:datepicker",
                },
            },
            {
                "name": "Shotgun Type",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11502",
                "clauseNames": ["cf[11502]", "Shotgun Type"],
                "orderable": True,
                "id": "customfield_11502",
                "schema": {
                    "customId": 11502,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                },
            },
            {
                "name": "Shotgun ID",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11501",
                "clauseNames": ["cf[11501]", "Shotgun ID"],
                "orderable": True,
                "id": "customfield_11501",
                "schema": {
                    "customId": 11501,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                },
            },
            {
                "name": "Changelist",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11504",
                "clauseNames": ["cf[11504]", "Changelist"],
                "orderable": True,
                "id": "customfield_11504",
                "schema": {
                    "customId": 11504,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textarea",
                },
            },
            {
                "name": "Shotgun URL",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11503",
                "clauseNames": ["cf[11503]", "Shotgun URL"],
                "orderable": True,
                "id": "customfield_11503",
                "schema": {
                    "customId": 11503,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:url",
                },
            },
            {
                "name": "Changelist3",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11506",
                "clauseNames": ["cf[11506]", "Changelist3"],
                "orderable": True,
                "id": "customfield_11506",
                "schema": {
                    "customId": 11506,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                },
            },
            {
                "name": "Affects Version/s",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "versions",
                "clauseNames": ["affectedVersion"],
                "orderable": True,
                "id": "versions",
                "schema": {
                    "items": "version",
                    "type": "array",
                    "system": "versions",
                },
            },
            {
                "name": "Changelist2",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11505",
                "clauseNames": ["cf[11505]", "Changelist2"],
                "orderable": True,
                "id": "customfield_11505",
                "schema": {
                    "customId": 11505,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                },
            },
            {
                "name": "Due Date",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11508",
                "clauseNames": ["cf[11508]", "Due Date"],
                "orderable": True,
                "id": "customfield_11508",
                "schema": {
                    "customId": 11508,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                },
            },
            {
                "name": "Changelist4",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11507",
                "clauseNames": ["cf[11507]", "Changelist4"],
                "orderable": True,
                "id": "customfield_11507",
                "schema": {
                    "customId": 11507,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textarea",
                },
            },
            {
                "name": "Fancy Due Date",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11509",
                "clauseNames": ["cf[11509]", "Fancy Due Date"],
                "orderable": True,
                "id": "customfield_11509",
                "schema": {
                    "customId": 11509,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                },
            },
            {
                "name": "Linked Issues",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "issuelinks",
                "clauseNames": [],
                "orderable": True,
                "id": "issuelinks",
                "schema": {
                    "items": "issuelinks",
                    "type": "array",
                    "system": "issuelinks",
                },
            },
            {
                "name": "Assignee",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "assignee",
                "clauseNames": ["assignee"],
                "orderable": True,
                "id": "assignee",
                "schema": {"type": "user", "system": "assignee"},
            },
            {
                "name": "Updated",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "updated",
                "clauseNames": ["updated", "updatedDate"],
                "orderable": False,
                "id": "updated",
                "schema": {"type": "datetime", "system": "updated"},
            },
            {
                "name": "Status",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "status",
                "clauseNames": ["status"],
                "orderable": False,
                "id": "status",
                "schema": {"type": "status", "system": "status"},
            },
            {
                "name": "Component/s",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "components",
                "clauseNames": ["component"],
                "orderable": True,
                "id": "components",
                "schema": {
                    "items": "component",
                    "type": "array",
                    "system": "components",
                },
            },
            {
                "name": "Key",
                "searchable": False,
                "navigable": True,
                "custom": False,
                "key": "issuekey",
                "clauseNames": ["id", "issue", "issuekey", "key"],
                "orderable": False,
                "id": "issuekey",
            },
            {
                "name": "Description",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "description",
                "clauseNames": ["description"],
                "orderable": True,
                "id": "description",
                "schema": {"type": "string", "system": "description"},
            },
            {
                "name": "Epic/Theme",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10010",
                "clauseNames": ["cf[10010]", "Epic/Theme"],
                "orderable": True,
                "id": "customfield_10010",
                "schema": {
                    "items": "string",
                    "customId": 10010,
                    "type": "array",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:labels",
                },
            },
            {
                "name": "Asset Type Old",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11100",
                "clauseNames": ["Asset Type Old", "cf[11100]"],
                "orderable": True,
                "id": "customfield_11100",
                "schema": {
                    "customId": 11100,
                    "type": "option",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:select",
                },
            },
            {
                "name": "Story Points",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10011",
                "clauseNames": ["cf[10011]", "Story Points"],
                "orderable": True,
                "id": "customfield_10011",
                "schema": {
                    "customId": 10011,
                    "type": "number",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:float",
                },
            },
            {
                "name": "Map / Level",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11101",
                "clauseNames": ["cf[11101]", "Map / Level"],
                "orderable": True,
                "id": "customfield_11101",
                "schema": {
                    "customId": 11101,
                    "type": "option",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:select",
                },
            },
            {
                "name": "Asset Type",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11300",
                "clauseNames": ["Asset Type", "cf[11300]"],
                "orderable": True,
                "id": "customfield_11300",
                "schema": {
                    "customId": 11300,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                },
            },
            {
                "name": "DEV Quality Target",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_11500",
                "clauseNames": ["cf[11500]", "DEV Quality Target"],
                "orderable": True,
                "id": "customfield_11500",
                "schema": {
                    "customId": 11500,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                },
            },
            {
                "name": "Epic Name",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10005",
                "clauseNames": ["cf[10005]", "Epic Name"],
                "orderable": True,
                "id": "customfield_10005",
                "schema": {
                    "customId": 10005,
                    "type": "string",
                    "custom": "com.pyxis.greenhopper.jira:gh-epic-label",
                },
            },
            {
                "name": "Epic Color",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10006",
                "clauseNames": ["cf[10006]", "Epic Color"],
                "orderable": True,
                "id": "customfield_10006",
                "schema": {
                    "customId": 10006,
                    "type": "string",
                    "custom": "com.pyxis.greenhopper.jira:gh-epic-color",
                },
            },
            {
                "name": "Development",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10600",
                "clauseNames": ["cf[10600]", "development"],
                "orderable": True,
                "id": "customfield_10600",
                "schema": {
                    "customId": 10600,
                    "type": "any",
                    "custom": "com.atlassian.jira.plugins.jira-development-integration-plugin:devsummarycf",
                },
            },
            {
                "name": "Security Level",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "security",
                "clauseNames": ["level"],
                "orderable": True,
                "id": "security",
                "schema": {"type": "securitylevel", "system": "security"},
            },
            {
                "name": "Rank",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10007",
                "clauseNames": ["cf[10007]", "Rank"],
                "orderable": True,
                "id": "customfield_10007",
                "schema": {
                    "customId": 10007,
                    "type": "any",
                    "custom": "com.pyxis.greenhopper.jira:gh-lexo-rank",
                },
            },
            {
                "name": "Organizations",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10800",
                "clauseNames": ["cf[10800]", "Organizations"],
                "orderable": True,
                "id": "customfield_10800",
                "schema": {
                    "items": "sd-customerorganization",
                    "customId": 10800,
                    "type": "array",
                    "custom": "com.atlassian.servicedesk:sd-customer-organizations",
                },
            },
            {
                "name": "Attachment",
                "searchable": True,
                "navigable": False,
                "custom": False,
                "key": "attachment",
                "clauseNames": ["attachments"],
                "orderable": True,
                "id": "attachment",
                "schema": {
                    "items": "attachment",
                    "type": "array",
                    "system": "attachment",
                },
            },
            {
                "name": "Flagged",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10009",
                "clauseNames": ["cf[10009]", "Flagged"],
                "orderable": True,
                "id": "customfield_10009",
                "schema": {
                    "items": "option",
                    "customId": 10009,
                    "type": "array",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:multicheckboxes",
                },
            },
            {
                "name": "Summary",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "summary",
                "clauseNames": ["summary"],
                "orderable": True,
                "id": "summary",
                "schema": {"type": "string", "system": "summary"},
            },
            {
                "name": "Creator",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "creator",
                "clauseNames": ["creator"],
                "orderable": False,
                "id": "creator",
                "schema": {"type": "user", "system": "creator"},
            },
            {
                "name": "Sub-tasks",
                "searchable": False,
                "navigable": True,
                "custom": False,
                "key": "subtasks",
                "clauseNames": ["subtasks"],
                "orderable": False,
                "id": "subtasks",
                "schema": {
                    "items": "issuelinks",
                    "type": "array",
                    "system": "subtasks",
                },
            },
            {
                "name": "Reporter",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "reporter",
                "clauseNames": ["reporter"],
                "orderable": True,
                "id": "reporter",
                "schema": {"type": "user", "system": "reporter"},
            },
            {
                "name": "[CHART] Date of First Response",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10000",
                "clauseNames": ["[CHART] Date of First Response", "cf[10000]"],
                "orderable": True,
                "id": "customfield_10000",
                "schema": {
                    "customId": 10000,
                    "type": "datetime",
                    "custom": "com.atlassian.jira.ext.charting:firstresponsedate",
                },
            },
            {
                "name": "[CHART] Time in Status",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10001",
                "clauseNames": ["[CHART] Time in Status", "cf[10001]"],
                "orderable": True,
                "id": "customfield_10001",
                "schema": {
                    "customId": 10001,
                    "type": "any",
                    "custom": "com.atlassian.jira.ext.charting:timeinstatus",
                },
            },
            {
                "name": "Sprint",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10002",
                "clauseNames": ["cf[10002]", "Sprint"],
                "orderable": True,
                "id": "customfield_10002",
                "schema": {
                    "items": "string",
                    "customId": 10002,
                    "type": "array",
                    "custom": "com.pyxis.greenhopper.jira:gh-sprint",
                },
            },
            {
                "name": "sg_type",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10200",
                "clauseNames": ["cf[10200]", "sg_type"],
                "orderable": True,
                "id": "customfield_10200",
                "schema": {
                    "customId": 10200,
                    "type": "string",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
                },
            },
            {
                "name": "Epic Link",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10003",
                "clauseNames": ["cf[10003]", "Epic Link"],
                "orderable": True,
                "id": "customfield_10003",
                "schema": {
                    "customId": 10003,
                    "type": "any",
                    "custom": "com.pyxis.greenhopper.jira:gh-epic-link",
                },
            },
            {
                "name": "POD",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10201",
                "clauseNames": ["cf[10201]", "POD"],
                "orderable": True,
                "id": "customfield_10201",
                "schema": {
                    "items": "option",
                    "customId": 10201,
                    "type": "array",
                    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:multiselect",
                },
            },
            {
                "name": "Approvals",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10400",
                "clauseNames": ["Approvals", "cf[10400]"],
                "orderable": True,
                "id": "customfield_10400",
                "schema": {
                    "customId": 10400,
                    "type": "sd-approvals",
                    "custom": "com.atlassian.servicedesk.approvals-plugin:sd-approvals",
                },
            },
            {
                "name": "Epic Status",
                "searchable": True,
                "navigable": True,
                "custom": True,
                "key": "customfield_10004",
                "clauseNames": ["cf[10004]", "Epic Status"],
                "orderable": True,
                "id": "customfield_10004",
                "schema": {
                    "customId": 10004,
                    "type": "option",
                    "custom": "com.pyxis.greenhopper.jira:gh-epic-status",
                },
            },
            {
                "name": "Environment",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "environment",
                "clauseNames": ["environment"],
                "orderable": True,
                "id": "environment",
                "schema": {"type": "string", "system": "environment"},
            },
            {
                "name": "Due date",
                "searchable": True,
                "navigable": True,
                "custom": False,
                "key": "duedate",
                "clauseNames": ["due", "duedate"],
                "orderable": True,
                "id": "duedate",
                "schema": {"type": "date", "system": "duedate"},
            },
            {
                "name": "Comment",
                "searchable": True,
                "navigable": False,
                "custom": False,
                "key": "comment",
                "clauseNames": ["comment"],
                "orderable": True,
                "id": "comment",
                "schema": {"type": "comments-page", "system": "comment"},
            },
            {
                "name": "Votes",
                "searchable": False,
                "navigable": True,
                "custom": False,
                "key": "votes",
                "clauseNames": ["votes"],
                "orderable": False,
                "id": "votes",
                "schema": {"type": "votes", "system": "votes"},
            },
            {
                "name": "Parent",
                "searchable": False,
                "navigable": True,
                "custom": False,
                "key": "parent",
                "clauseNames": ["parent"],
                "orderable": False,
                "id": "parent",
            }
        ]

    def create_issue(self, fields, *args, **kwargs):
        """
        Mocked Jira method.
        Return a :class:`JiraIssue`.
        """
        issue_key = "FAKED-%03d" % len(self._issues)
        raw = copy.deepcopy(ISSUE_BASE_RAW)
        raw["fields"].update(fields)
        raw["id"] = "%s" % len(self._issues)
        raw["key"] = issue_key
        raw["self"] = "https://mocked.faked.com/rest/api/2/issue/%s" % raw["id"]

        self._issues[issue_key] = MockedIssue(
            RESOURCE_OPTIONS,
            MockedSession(),
            raw=raw,
        )
        self._issues[issue_key].key = issue_key
        self._issues[issue_key].id = len(self._issues)
        return self._issues[issue_key]

    def create_issue_link(self, type, inwardIssue, outwardIssue, comment=None):
        """
        Mocked Jira method.
        """
        issue_link = {
            "id": len(self._issue_links),
            "type": {"name": type},
            "inwardIssue": {"key": inwardIssue},
            "outwardIssue": {"key": outwardIssue},
            "comment": comment,
        }
        self._issue_links.append(issue_link)
        issue = self.issue(inwardIssue)
        issue.update(
            fields={
                "issuelinks": issue.fields.issuelinks
                + [IssueLink(None, None, raw=issue_link)]
            }
        )
        issue = self.issue(outwardIssue)
        issue.update(
            fields={
                "issuelinks": issue.fields.issuelinks
                + [IssueLink(None, None, raw=issue_link)]
            }
        )
        return issue_link

    def delete_issue_link(self, id):
        """
        Mocked Jira method.
        """
        issue_link = IssueLink(None, None, self._issue_links.pop(id))
        issue = self.issue(issue_link.inwardIssue.key)
        keep_links = []
        for link in issue.fields.issuelinks:
            if link.id != issue_link.id:
                keep_links.append(link)
        issue.update(fields={"issuelinks": keep_links})
        issue = self.issue(issue_link.outwardIssue.key)
        keep_links = []
        for link in issue.fields.issuelinks:
            if link.id != issue_link.id:
                keep_links.append(link)
        issue.update(fields={"issuelinks": keep_links})

    def issue(self, issue_key, *args, **kwargs):
        """
        Mocked Jira method.
        """
        if isinstance(issue_key, jira.resources.Issue):
            issue_key = issue_key.key
        if issue_key not in self._issues:
            raise jira.JIRAError(text="Unable to find Issue %s" % issue_key, status_code=404)
        return self._issues.get(issue_key)

    def add_comment(self, issue, body, *args, **kwargs):
        """
        Mocked Jira method.
        """
        if not isinstance(issue, jira.resources.Issue):
            issue = self.issue(issue)
        raw = {"issue": issue, "id": str(len(issue._comments) + 1), "body": body}
        for k in kwargs:
            raw[k] = kwargs[k]
        comment = MockedComment(None, None, raw=raw)
        issue._comments.append(comment)
        return comment

    def comment(self, issue_key, comment_id, *args, **kwargs):
        """
        Mocked Jira method.
        """
        issue = self.issue(issue_key)
        for c in issue._comments:
            if c.id == comment_id:
                return c
        return None

    def add_worklog(self, issue, *args, **kwargs):
        """Mocked Jira method to add a worklog"""
        if not isinstance(issue, jira.resources.Issue):
            issue = self.issue(issue)
        raw = {"issue": issue, "id": str(len(issue._worklogs) + 1)}
        for k in kwargs:
            raw[k] = kwargs[k]
        worklog = MockedWorklog(None, None, raw=raw)
        issue._worklogs.append(worklog)
        return worklog

    def worklog(self, issue_key, worklog_key):
        """Mocked Jira method to retrieve a worklog associated with an issue"""
        issue = self.issue(issue_key) if not isinstance(issue_key, jira.resources.Issue) else issue_key
        for w in issue._worklogs:
            if w.id == worklog_key:
                return w
        return None

    def worklogs(self, issue_key):
        """Mocked Jira method to retrieve all the worklogs associated with an issue"""
        issue = self.issue(issue_key)
        return issue._worklogs

    def comments(self, issue_key):
        """Mocked Jira method to retrieve all the comments associated with an issue"""
        issue = self.issue(issue_key)
        return issue._comments

    def transitions(self, *args, **kwargs):
        """
        Mocked Jira method.
        """
        return [
            {
                "id": 1,
                "name": "From Fake",
                "to": {"name": "To Do"},
            }
        ]

    def transition_issue(self, jira_issue, transition_id, *args, **kwargs):
        for t in self.transitions():
            if t["id"] == transition_id:
                jira_issue.update(
                    fields={
                        "status": Status(None, None, raw={"name": t["to"]["name"]})
                    }
                )

    def search_assignable_users_for_issues(
        self, username=None, query=None, startAt=0, maxResults=20, *args, **kwargs
    ):
        """
        Mocked Jira method.
        Return a list :class:`JiraUser`.
        """
        options = {"deployment_type": "Cloud" if self.is_jira_cloud else "Server"}

        if username:
            # Mock Jira REST api bug
            return []

        elif query == JIRA_USER["emailAddress"]:
            return [User(options, None, JIRA_USER)]

        elif query == JIRA_USER_2["emailAddress"]:
            return [User(options, None, JIRA_USER_2)]
        else:
            return []

    def user(self, id, payload="username"):
        """
        Mocked Jira method.
        Return :class:`JiraUser`.
        """
        if payload not in ["accountId", "username", "key"]:
            raise RuntimeError("Unknown payload type: {}".format(payload))

        # The endpoint parameter was username, but the field we need to look up is actually
        # "name".
        if payload == "username":
            payload = "name"

        options = {"deployment_type": "Cloud" if self.is_jira_cloud else "Server"}

        if id == JIRA_USER[payload]:
            return User(options, None, JIRA_USER)
        if id == JIRA_USER_2[payload]:
            return User(options, None, JIRA_USER_2)
        return None

    def search_issues(self, jql_str):
        """
        Mocked Jira method
        """

        result = re.search(r"parent IN \(\'([\w-]+)\'\)", jql_str)

        if result:
            return [self.issue(result.group(1))]