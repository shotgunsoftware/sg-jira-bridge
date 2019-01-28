# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import copy
from jira.resources import Project as JiraProject
from jira.resources import IssueType, Issue, User

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
    "expand": "description,lead,issueTypes,url,projectKeys"
}

JIRA_USER = {
    "accountId": "abdc123456",
    "active": True,
    "displayName": "Ford Prefect",
    "emailAddress": "fprefect@weefree.com",
    "key": "ford.prefect1",
    "name": "ford.prefect1",
    "self": "https://myjira.atlassian.net/rest/api/2/user?accountId=abdc123456",
    "timeZone": "Europe/Paris"
}

JIRA_USER_2 = {
    "accountId": "12343456778",
    "active": True,
    "displayName": "Sync Sync",
    "emailAddress": "syncsync.@foo.com",
    "key": "sync-sync",
    "name": "sync-sync",
    "self": "https://myjira.atlassian.net/rest/api/2/user?accountId=12343456778",
    "timeZone": "America/New_York"
}

ISSUE_FIELDS = {
    "assignee": {
        "autoCompleteUrl": "https://mocked.faked.com/rest/api/latest/user/assignable/search?project=ST3&query=",
        "hasDefaultValue": False,
        "key": "assignee",
        "name": "Assignee",
        "operations": ["set"],
        "required": False,
        "schema": {"system": "assignee", "type": "user"}
    },
    "attachment": {
        "hasDefaultValue": False,
        "key": "attachment",
        "name": "Attachment",
        "operations": [],
        "required": False,
        "schema": {"items": "attachment", "system": "attachment", "type": "array"}
    },
    "components": {
        "allowedValues": [],
        "hasDefaultValue": False,
        "key": "components",
        "name": "Component/s",
        "operations": [
            "add",
            "set",
            "remove"
        ],
        "required": False,
        "schema": {"items": "component", "system": "components", "type": "array"}
    },
    "customfield_10003": {
        "hasDefaultValue": False,
        "key": "customfield_10003",
        "name": "Epic Link",
        "operations": [
            "set"
        ],
        "required": False,
        "schema": {"custom": "com.pyxis.greenhopper.jira:gh-epic-link", "customId": 10003, "type": "any"}
    },
    "customfield_11501": {
        "hasDefaultValue": False,
        "key": "customfield_11501",
        "name": "Shotgun ID",
        "operations": [
            "set"
        ],
        "required": False,
        "schema": {"custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield", "customId": 11501, "type": "string"}
    },
    "customfield_11502": {
        "hasDefaultValue": False,
        "key": "customfield_11502",
        "name": "Shotgun Type",
        "operations": [
            "set"
        ],
        "required": False,
        "schema": {
            "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
            "customId": 11502,
            "type": "string"
        }
    },
    "description": {
        "hasDefaultValue": False,
        "key": "description",
        "name": "Description",
        "operations": [
            "set"
        ],
        "required": False,
        "schema": {"system": "description", "type": "string"}
    },
    "fixVersions": {
        "allowedValues": [],
        "hasDefaultValue": False,
        "key": "fixVersions",
        "name": "Fix Version/s",
        "operations": [
            "set",
            "add",
            "remove"
        ],
        "required": False,
        "schema": {"items": "version", "system": "fixVersions", "type": "array"}
    },
    "issuelinks": {
        "autoCompleteUrl": "https://mocked.faked.com/rest/api/2/issue/picker?currentProjectId=&showSubTaskParent=true&showSubTasks=true&currentIssueKey=null&query=",
        "hasDefaultValue": False,
        "key": "issuelinks",
        "name": "Linked Issues",
        "operations": [
            "add"
        ],
        "required": False,
        "schema": {"items": "issuelinks", "system": "issuelinks", "type": "array"}
    },
    "issuetype": {
        "allowedValues": [{
            "avatarId": 10318,
            "description": "A task that needs to be done.",
            "iconUrl": "https://mocked.faked.com/secure/viewavatar?size=xsmall&avatarId=10318&avatarType=issuetype",
            "id": "10000",
            "name": "Task",
            "self": "https://mocked.faked.com/rest/api/2/issuetype/10000",
            "subtask": False
        }],
        "hasDefaultValue": False,
        "key": "issuetype",
        "name": "Issue Type",
        "operations": [],
        "required": True,
        "schema": {"system": "issuetype", "type": "issuetype"}
    },
    "labels": {
        "autoCompleteUrl": "https://mocked.faked.com/rest/api/1.0/labels/suggest?query=",
        "hasDefaultValue": False,
        "key": "labels",
        "name": "Labels",
        "operations": [
            "add",
            "set",
            "remove"
        ],
        "required": False,
        "schema": {"items": "string", "system": "labels", "type": "array"}
    },
    "priority": {
        "allowedValues": [
            {
                "iconUrl": "https://mocked.faked.com/images/icons/priorities/highest.svg",
                "id": "1",
                "name": "Highest",
                "self": "https://mocked.faked.com/rest/api/2/priority/1"
            },
            {
                "iconUrl": "https://mocked.faked.com/images/icons/priorities/high.svg",
                "id": "2",
                "name": "High",
                "self": "https://mocked.faked.com/rest/api/2/priority/2"
            },
            {
                "iconUrl": "https://mocked.faked.com/images/icons/priorities/medium.svg",
                "id": "3",
                "name": "Medium",
                "self": "https://mocked.faked.com/rest/api/2/priority/3"
            },
            {
                "iconUrl": "https://mocked.faked.com/images/icons/priorities/low.svg",
                "id": "4",
                "name": "Low",
                "self": "https://mocked.faked.com/rest/api/2/priority/4"
            },
            {
                "iconUrl": "https://mocked.faked.com/images/icons/priorities/lowest.svg",
                "id": "5",
                "name": "Lowest",
                "self": "https://mocked.faked.com/rest/api/2/priority/5"
            }
        ],
        "defaultValue": {
            "iconUrl": "https://mocked.faked.com/images/icons/priorities/medium.svg",
            "id": "3",
            "name": "Medium",
            "self": "https://mocked.faked.com/rest/api/2/priority/3"
        },
        "hasDefaultValue": True,
        "key": "priority",
        "name": "Priority",
        "operations": [
            "set"
        ],
        "required": True,
        "schema": {
            "system": "priority",
            "type": "priority"
        }
    },
    "project": {
        "allowedValues": [
            {
                "avatarUrls": {
                    "16x16": "https://mocked.faked.com/secure/projectavatar?size=xsmall&avatarId=10324",
                    "24x24": "https://mocked.faked.com/secure/projectavatar?size=small&avatarId=10324",
                    "32x32": "https://mocked.faked.com/secure/projectavatar?size=medium&avatarId=10324",
                    "48x48": "https://mocked.faked.com/secure/projectavatar?avatarId=10324"
                },
                "id": "11112",
                "key": "ST3",
                "name": "Steph Tests 3",
                "projectTypeKey": "software",
                "self": "https://mocked.faked.com/rest/api/2/project/11112"
            }
        ],
        "hasDefaultValue": False,
        "key": "project",
        "name": "Project",
        "operations": [
            "set"
        ],
        "required": True,
        "schema": {
            "system": "project",
            "type": "project"
        }
    },
    "reporter": {
        "autoCompleteUrl": "https://mocked.faked.com/rest/api/latest/user/search?query=",
        "hasDefaultValue": True,
        "key": "reporter",
        "name": "Reporter",
        "operations": [
            "set"
        ],
        "required": False,
        "schema": {
            "system": "reporter",
            "type": "user"
        }
    },
    "summary": {
        "hasDefaultValue": False,
        "key": "summary",
        "name": "Summary",
        "operations": [
            "set"
        ],
        "required": True,
        "schema": {
            "system": "summary",
            "type": "string"
        }
    }
}

TASK_CREATE_META = {
    "description": "A task that needs to be done.",
    "expand": "fields",
    "fields": ISSUE_FIELDS,
    "iconUrl": "https://mocked.faked.com/secure/viewavatar?size=xsmall&avatarId=10318&avatarType=issuetype",
    "id": "10000",
    "name": "Task",
    "self": "https://mocked.faked.com/rest/api/2/issuetype/10000",
    "subtask": False
}

TASK_EDIT_META = {
    "fields": ISSUE_FIELDS
}

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
            "timeZone": "America/New_York"
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
            "subtask": False
        },
        "labels": [],
        "lastViewed": "2018-12-18T09:44:27.653-0500",
        "priority": {
            "iconUrl": "https://myjira.atlassian.net/images/icons/priorities/medium.svg",
            "id": "3",
            "name": "Medium",
            "self": "https://myjira.atlassian.net/rest/api/2/priority/3"
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
            "timeZone": "America/New_York"
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
                "self": "https://myjira.atlassian.net/rest/api/2/statuscategory/2"
            }
        },
        "subtasks": [],
        "summary": "foo bar",
        "updated": "2018-12-18T09:44:27.572-0500",
        "versions": [],
        "votes": {
            "hasVoted": False,
            "self": "https://myjira.atlassian.net/rest/api/2/issue/ST3-4/votes",
            "votes": 0
        },
        "watches": {
            "isWatching": False,
            "self": "https://myjira.atlassian.net/rest/api/2/issue/ST3-4/watchers",
            "watchCount": 1
        },
        "workratio": -1
    },
}

RESOURCE_OPTIONS = {
    u'rest_api_version': u'2',
    u'agile_rest_api_version': u'1.0',
    u'verify': True,
    u'context_path': u'/',
    u'agile_rest_path':
    u'greenhopper',
    u'server': u'https://sgpipeline.atlassian.net',
    u'check_update': False,
    u'headers': {u'Content-Type': u'application/json', u'X-Atlassian-Token': u'no-check', u'Cache-Control': u'no-cache'},
    u'auth_url': u'/rest/auth/1/session',
    u'async_workers': 5,
    u'resilient': True,
    u'async': False,
    u'client_cert': None,
    u'rest_path': u'api'
}


class MockedSession(object):
    def put(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return {}


class MockedIssue(Issue):
    def update(self, fields, *args, **kwargs):
        raw = self.raw
        raw["fields"].update(fields)
        self._parse_raw(raw)


class MockedJira(object):
    """
    A class to mock a Jira connection and methods used by the bridge.
    """
    def __init__(self, *args, **kwargs):
        self._projects = []
        self._createmeta = {}
        self._issues = {}

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
            self._projects.append(
                JiraProject(
                    None,
                    None,
                    raw=project
                )
            )

    def projects(self):
        """
        Mocked Jira method.
        Return a list of :class:`JiraProject`.
        """
        return self._projects

    def createmeta(self, *args, **kwargs):
        """
        Mocked Jira method.
        Return a dictionary with create metadata for all projects.
        """
        projects_meta = []
        for project in self._projects:
            projects_meta.append({
                "key": project.key,
                "name": project.name,
                "self": "https://mocked.faked.com/rest/api/2/project/%s" % project.id,
                "expand": "issuetypes",
                "id": project.id,
                "issuetypes": [TASK_CREATE_META],
            })

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

    def issue_type_by_name(self, name):
        """
        Mocked Jira method.
        Return a :class:`IssueType`.
        """
        return IssueType(None, None, raw={
            "name": name,
            "id": 12345
        })

    def current_user(self):
        """
        Mocked Jira method.
        Return a string.
        """
        return "ford.prefect1"

    def fields(self):
        """
        Mocked Jira method.
        Return a list of dictionaries.
        """
        return [
            {u'name': u'Issue Type', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'issuetype', u'clauseNames': [u'issuetype', u'type'], u'orderable': True, u'id': u'issuetype', u'schema': {u'type': u'issuetype', u'system': u'issuetype'}},
            {u'name': u'Project', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'project', u'clauseNames': [u'project'], u'orderable': False, u'id': u'project', u'schema': {u'type': u'project', u'system': u'project'}},
            {u'name': u'test extra text', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11000', u'clauseNames': [u'cf[11000]', u'test extra text'], u'orderable': True, u'id': u'customfield_11000', u'schema': {u'customId': 11000, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textfield'}},
            {u'name': u'Fix Version/s', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'fixVersions', u'clauseNames': [u'fixVersion'], u'orderable': True, u'id': u'fixVersions', u'schema': {u'items': u'version', u'type': u'array', u'system': u'fixVersions'}},
            {u'name': u'Resolution', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'resolution', u'clauseNames': [u'resolution'], u'orderable': True, u'id': u'resolution', u'schema': {u'type': u'resolution', u'system': u'resolution'}},
            {u'name': u'Implementation Details', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11400', u'clauseNames': [u'cf[11400]', u'Implementation Details'], u'orderable': True, u'id': u'customfield_11400', u'schema': {u'customId': 11400, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textarea'}},
            {u'name': u'Parent Link', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10500', u'clauseNames': [u'cf[10500]', u'Parent Link'], u'orderable': True, u'id': u'customfield_10500', u'schema': {u'customId': 10500, u'type': u'any', u'custom': u'com.atlassian.jpo:jpo-custom-field-parent'}},
            {u'name': u'Request Type', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11513', u'clauseNames': [u'cf[11513]', u'Request Type'], u'orderable': True, u'id': u'customfield_11513', u'schema': {u'customId': 11513, u'type': u'sd-customerrequesttype', u'custom': u'com.atlassian.servicedesk:vp-origin'}},
            {u'name': u'Start date', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11512', u'clauseNames': [u'cf[11512]', u'Start date'], u'orderable': True, u'id': u'customfield_11512', u'schema': {u'customId': 11512, u'type': u'date', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:datepicker'}},
            {u'name': u'Story point estimate', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11515', u'clauseNames': [u'cf[11515]', u'Story point estimate'], u'orderable': True, u'id': u'customfield_11515', u'schema': {u'customId': 11515, u'type': u'number', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:float'}},
            {u'name': u'Team', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10700', u'clauseNames': [u'cf[10700]', u'Team'], u'orderable': True, u'id': u'customfield_10700', u'schema': {u'customId': 10700, u'type': u'any', u'custom': u'com.atlassian.teams:rm-teams-custom-field-team'}},
            {u'name': u'Request participants', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11514', u'clauseNames': [u'cf[11514]', u'Request participants'], u'orderable': True, u'id': u'customfield_11514', u'schema': {u'items': u'user', u'customId': 11514, u'type': u'array', u'custom': u'com.atlassian.servicedesk:sd-request-participants'}},
            {u'name': u'Level', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10900', u'clauseNames': [u'cf[10900]'], u'orderable': True, u'id': u'customfield_10900', u'schema': {u'customId': 10900, u'type': u'option', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:select'}},
            {u'name': u'Issue color', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11516', u'clauseNames': [u'cf[11516]', u'Issue color'], u'orderable': True, u'id': u'customfield_11516', u'schema': {u'customId': 11516, u'type': u'string', u'custom': u'com.pyxis.greenhopper.jira:jsw-issue-color'}},
            {u'name': u'Resolved', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'resolutiondate', u'clauseNames': [u'resolutiondate', u'resolved'], u'orderable': False, u'id': u'resolutiondate', u'schema': {u'type': u'datetime', u'system': u'resolutiondate'}},
            {u'name': u'Work Ratio', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'workratio', u'clauseNames': [u'workratio'], u'orderable': False, u'id': u'workratio', u'schema': {u'type': u'number', u'system': u'workratio'}},
            {u'name': u'Last Viewed', u'searchable': False, u'navigable': True, u'custom': False, u'key': u'lastViewed', u'clauseNames': [u'lastViewed'], u'orderable': False, u'id': u'lastViewed', u'schema': {u'type': u'datetime', u'system': u'lastViewed'}},
            {u'name': u'Watchers', u'searchable': False, u'navigable': True, u'custom': False, u'key': u'watches', u'clauseNames': [u'watchers'], u'orderable': False, u'id': u'watches', u'schema': {u'type': u'watches', u'system': u'watches'}},
            {u'name': u'Images', u'searchable': False, u'navigable': True, u'custom': False, u'key': u'thumbnail', u'clauseNames': [], u'orderable': False, u'id': u'thumbnail'},
            {u'name': u'Created', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'created', u'clauseNames': [u'created', u'createdDate'], u'orderable': False, u'id': u'created', u'schema': {u'type': u'datetime', u'system': u'created'}},
            {u'name': u'Priority', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'priority', u'clauseNames': [u'priority'], u'orderable': True, u'id': u'priority', u'schema': {u'type': u'priority', u'system': u'priority'}},
            {u'name': u'sg_key', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10100', u'clauseNames': [u'cf[10100]', u'sg_key'], u'orderable': True, u'id': u'customfield_10100', u'schema': {u'customId': 10100, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textfield'}},
            {u'name': u'test_int', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10101', u'clauseNames': [u'cf[10101]', u'test_int'], u'orderable': True, u'id': u'customfield_10101', u'schema': {u'customId': 10101, u'type': u'number', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:float'}},
            {u'name': u'Shotgun Status', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11511', u'clauseNames': [u'cf[11511]', u'Shotgun Status'], u'orderable': True, u'id': u'customfield_11511', u'schema': {u'customId': 11511, u'type': u'option', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:select'}},
            {u'name': u'sg_url', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10300', u'clauseNames': [u'cf[10300]', u'sg_url'], u'orderable': True, u'id': u'customfield_10300', u'schema': {u'customId': 10300, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:url'}},
            {u'name': u'Labels', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'labels', u'clauseNames': [u'labels'], u'orderable': True, u'id': u'labels', u'schema': {u'items': u'string', u'type': u'array', u'system': u'labels'}},
            {u'name': u'Fancy Due Date 2', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11510', u'clauseNames': [u'cf[11510]', u'Fancy Due Date 2'], u'orderable': True, u'id': u'customfield_11510', u'schema': {u'customId': 11510, u'type': u'date', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:datepicker'}},
            {u'name': u'Shotgun Type', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11502', u'clauseNames': [u'cf[11502]', u'Shotgun Type'], u'orderable': True, u'id': u'customfield_11502', u'schema': {u'customId': 11502, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textfield'}},
            {u'name': u'Shotgun ID', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11501', u'clauseNames': [u'cf[11501]', u'Shotgun ID'], u'orderable': True, u'id': u'customfield_11501', u'schema': {u'customId': 11501, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textfield'}},
            {u'name': u'Changelist', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11504', u'clauseNames': [u'cf[11504]', u'Changelist'], u'orderable': True, u'id': u'customfield_11504', u'schema': {u'customId': 11504, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textarea'}},
            {u'name': u'Shotgun URL', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11503', u'clauseNames': [u'cf[11503]', u'Shotgun URL'], u'orderable': True, u'id': u'customfield_11503', u'schema': {u'customId': 11503, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:url'}},
            {u'name': u'Changelist3', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11506', u'clauseNames': [u'cf[11506]', u'Changelist3'], u'orderable': True, u'id': u'customfield_11506', u'schema': {u'customId': 11506, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textfield'}},
            {u'name': u'Affects Version/s', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'versions', u'clauseNames': [u'affectedVersion'], u'orderable': True, u'id': u'versions', u'schema': {u'items': u'version', u'type': u'array', u'system': u'versions'}},
            {u'name': u'Changelist2', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11505', u'clauseNames': [u'cf[11505]', u'Changelist2'], u'orderable': True, u'id': u'customfield_11505', u'schema': {u'customId': 11505, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textfield'}},
            {u'name': u'Due Date', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11508', u'clauseNames': [u'cf[11508]', u'Due Date'], u'orderable': True, u'id': u'customfield_11508', u'schema': {u'customId': 11508, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textfield'}},
            {u'name': u'Changelist4', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11507', u'clauseNames': [u'cf[11507]', u'Changelist4'], u'orderable': True, u'id': u'customfield_11507', u'schema': {u'customId': 11507, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textarea'}},
            {u'name': u'Fancy Due Date', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11509', u'clauseNames': [u'cf[11509]', u'Fancy Due Date'], u'orderable': True, u'id': u'customfield_11509', u'schema': {u'customId': 11509, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textfield'}},
            {u'name': u'Linked Issues', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'issuelinks', u'clauseNames': [], u'orderable': True, u'id': u'issuelinks', u'schema': {u'items': u'issuelinks', u'type': u'array', u'system': u'issuelinks'}},
            {u'name': u'Assignee', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'assignee', u'clauseNames': [u'assignee'], u'orderable': True, u'id': u'assignee', u'schema': {u'type': u'user', u'system': u'assignee'}},
            {u'name': u'Updated', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'updated', u'clauseNames': [u'updated', u'updatedDate'], u'orderable': False, u'id': u'updated', u'schema': {u'type': u'datetime', u'system': u'updated'}},
            {u'name': u'Status', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'status', u'clauseNames': [u'status'], u'orderable': False, u'id': u'status', u'schema': {u'type': u'status', u'system': u'status'}},
            {u'name': u'Component/s', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'components', u'clauseNames': [u'component'], u'orderable': True, u'id': u'components', u'schema': {u'items': u'component', u'type': u'array', u'system': u'components'}},
            {u'name': u'Key', u'searchable': False, u'navigable': True, u'custom': False, u'key': u'issuekey', u'clauseNames': [u'id', u'issue', u'issuekey', u'key'], u'orderable': False, u'id': u'issuekey'},
            {u'name': u'Description', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'description', u'clauseNames': [u'description'], u'orderable': True, u'id': u'description', u'schema': {u'type': u'string', u'system': u'description'}},
            {u'name': u'Epic/Theme', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10010', u'clauseNames': [u'cf[10010]', u'Epic/Theme'], u'orderable': True, u'id': u'customfield_10010', u'schema': {u'items': u'string', u'customId': 10010, u'type': u'array', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:labels'}},
            {u'name': u'Asset Type Old', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11100', u'clauseNames': [u'Asset Type Old', u'cf[11100]'], u'orderable': True, u'id': u'customfield_11100', u'schema': {u'customId': 11100, u'type': u'option', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:select'}},
            {u'name': u'Story Points', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10011', u'clauseNames': [u'cf[10011]', u'Story Points'], u'orderable': True, u'id': u'customfield_10011', u'schema': {u'customId': 10011, u'type': u'number', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:float'}},
            {u'name': u'Map / Level', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11101', u'clauseNames': [u'cf[11101]', u'Map / Level'], u'orderable': True, u'id': u'customfield_11101', u'schema': {u'customId': 11101, u'type': u'option', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:select'}},
            {u'name': u'Asset Type', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11300', u'clauseNames': [u'Asset Type', u'cf[11300]'], u'orderable': True, u'id': u'customfield_11300', u'schema': {u'customId': 11300, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textfield'}},
            {u'name': u'DEV Quality Target', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_11500', u'clauseNames': [u'cf[11500]', u'DEV Quality Target'], u'orderable': True, u'id': u'customfield_11500', u'schema': {u'customId': 11500, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textfield'}},
            {u'name': u'Epic Name', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10005', u'clauseNames': [u'cf[10005]', u'Epic Name'], u'orderable': True, u'id': u'customfield_10005', u'schema': {u'customId': 10005, u'type': u'string', u'custom': u'com.pyxis.greenhopper.jira:gh-epic-label'}},
            {u'name': u'Epic Color', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10006', u'clauseNames': [u'cf[10006]', u'Epic Color'], u'orderable': True, u'id': u'customfield_10006', u'schema': {u'customId': 10006, u'type': u'string', u'custom': u'com.pyxis.greenhopper.jira:gh-epic-color'}},
            {u'name': u'Development', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10600', u'clauseNames': [u'cf[10600]', u'development'], u'orderable': True, u'id': u'customfield_10600', u'schema': {u'customId': 10600, u'type': u'any', u'custom': u'com.atlassian.jira.plugins.jira-development-integration-plugin:devsummarycf'}},
            {u'name': u'Security Level', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'security', u'clauseNames': [u'level'], u'orderable': True, u'id': u'security', u'schema': {u'type': u'securitylevel', u'system': u'security'}},
            {u'name': u'Rank', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10007', u'clauseNames': [u'cf[10007]', u'Rank'], u'orderable': True, u'id': u'customfield_10007', u'schema': {u'customId': 10007, u'type': u'any', u'custom': u'com.pyxis.greenhopper.jira:gh-lexo-rank'}},
            {u'name': u'Organizations', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10800', u'clauseNames': [u'cf[10800]', u'Organizations'], u'orderable': True, u'id': u'customfield_10800', u'schema': {u'items': u'sd-customerorganization', u'customId': 10800, u'type': u'array', u'custom': u'com.atlassian.servicedesk:sd-customer-organizations'}},
            {u'name': u'Attachment', u'searchable': True, u'navigable': False, u'custom': False, u'key': u'attachment', u'clauseNames': [u'attachments'], u'orderable': True, u'id': u'attachment', u'schema': {u'items': u'attachment', u'type': u'array', u'system': u'attachment'}},
            {u'name': u'Flagged', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10009', u'clauseNames': [u'cf[10009]', u'Flagged'], u'orderable': True, u'id': u'customfield_10009', u'schema': {u'items': u'option', u'customId': 10009, u'type': u'array', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:multicheckboxes'}},
            {u'name': u'Summary', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'summary', u'clauseNames': [u'summary'], u'orderable': True, u'id': u'summary', u'schema': {u'type': u'string', u'system': u'summary'}},
            {u'name': u'Creator', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'creator', u'clauseNames': [u'creator'], u'orderable': False, u'id': u'creator', u'schema': {u'type': u'user', u'system': u'creator'}},
            {u'name': u'Sub-tasks', u'searchable': False, u'navigable': True, u'custom': False, u'key': u'subtasks', u'clauseNames': [u'subtasks'], u'orderable': False, u'id': u'subtasks', u'schema': {u'items': u'issuelinks', u'type': u'array', u'system': u'subtasks'}},
            {u'name': u'Reporter', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'reporter', u'clauseNames': [u'reporter'], u'orderable': True, u'id': u'reporter', u'schema': {u'type': u'user', u'system': u'reporter'}},
            {u'name': u'[CHART] Date of First Response', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10000', u'clauseNames': [u'[CHART] Date of First Response', u'cf[10000]'], u'orderable': True, u'id': u'customfield_10000', u'schema': {u'customId': 10000, u'type': u'datetime', u'custom': u'com.atlassian.jira.ext.charting:firstresponsedate'}},
            {u'name': u'[CHART] Time in Status', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10001', u'clauseNames': [u'[CHART] Time in Status', u'cf[10001]'], u'orderable': True, u'id': u'customfield_10001', u'schema': {u'customId': 10001, u'type': u'any', u'custom': u'com.atlassian.jira.ext.charting:timeinstatus'}},
            {u'name': u'Sprint', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10002', u'clauseNames': [u'cf[10002]', u'Sprint'], u'orderable': True, u'id': u'customfield_10002', u'schema': {u'items': u'string', u'customId': 10002, u'type': u'array', u'custom': u'com.pyxis.greenhopper.jira:gh-sprint'}},
            {u'name': u'sg_type', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10200', u'clauseNames': [u'cf[10200]', u'sg_type'], u'orderable': True, u'id': u'customfield_10200', u'schema': {u'customId': 10200, u'type': u'string', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:textfield'}},
            {u'name': u'Epic Link', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10003', u'clauseNames': [u'cf[10003]', u'Epic Link'], u'orderable': True, u'id': u'customfield_10003', u'schema': {u'customId': 10003, u'type': u'any', u'custom': u'com.pyxis.greenhopper.jira:gh-epic-link'}},
            {u'name': u'POD', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10201', u'clauseNames': [u'cf[10201]', u'POD'], u'orderable': True, u'id': u'customfield_10201', u'schema': {u'items': u'option', u'customId': 10201, u'type': u'array', u'custom': u'com.atlassian.jira.plugin.system.customfieldtypes:multiselect'}},
            {u'name': u'Approvals', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10400', u'clauseNames': [u'Approvals', u'cf[10400]'], u'orderable': True, u'id': u'customfield_10400', u'schema': {u'customId': 10400, u'type': u'sd-approvals', u'custom': u'com.atlassian.servicedesk.approvals-plugin:sd-approvals'}},
            {u'name': u'Epic Status', u'searchable': True, u'navigable': True, u'custom': True, u'key': u'customfield_10004', u'clauseNames': [u'cf[10004]', u'Epic Status'], u'orderable': True, u'id': u'customfield_10004', u'schema': {u'customId': 10004, u'type': u'option', u'custom': u'com.pyxis.greenhopper.jira:gh-epic-status'}},
            {u'name': u'Environment', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'environment', u'clauseNames': [u'environment'], u'orderable': True, u'id': u'environment', u'schema': {u'type': u'string', u'system': u'environment'}},
            {u'name': u'Due date', u'searchable': True, u'navigable': True, u'custom': False, u'key': u'duedate', u'clauseNames': [u'due', u'duedate'], u'orderable': True, u'id': u'duedate', u'schema': {u'type': u'date', u'system': u'duedate'}},
            {u'name': u'Comment', u'searchable': True, u'navigable': False, u'custom': False, u'key': u'comment', u'clauseNames': [u'comment'], u'orderable': True, u'id': u'comment', u'schema': {u'type': u'comments-page', u'system': u'comment'}},
            {u'name': u'Votes', u'searchable': False, u'navigable': True, u'custom': False, u'key': u'votes', u'clauseNames': [u'votes'], u'orderable': False, u'id': u'votes', u'schema': {u'type': u'votes', u'system': u'votes'}},
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

    def issue(self, issue_key, *args, **kwargs):
        """
        Mocked Jira method.
        """
        return self._issues.get(issue_key)

    def transitions(self, *args, **kwargs):
        """
        Mocked Jira method.
        """
        return []

    def search_assignable_users_for_issues(self, name, startAt=0, maxResults=20, *args, **kwargs):
        """
        Mocked Jira method.
        Return a list :class:`JiraUser`.
        """
        if name:
            # Mock Jira REST api bug
            return []

        if startAt == 0:
            return [User(None, None, JIRA_USER_2)] * maxResults
        return [User(None, None, JIRA_USER)]
