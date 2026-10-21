# Copyright 2026 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import unittest
from unittest import mock

from sg_jira.constants import (
    JIRA_PROJECT_AUTOMATION_SOURCE,
    JIRA_SYNC_IN_FPTR_FIELD,
)
from sg_jira.jira_automation_payload import (
    JiraAutomationPayloadError,
    normalize_automation_request,
)


class MockJiraIssue:
    id = "10001"


class MockJira:
    def __init__(self):
        self._fields_map = {
            "summary": "summary",
            JIRA_SYNC_IN_FPTR_FIELD.lower(): "customfield_sync",
        }

    def issue(self, key, expand=None):
        issue = mock.Mock()
        issue.id = MockJiraIssue.id
        return issue

    def get_jira_issue_field_id(self, name):
        return self._fields_map.get(name.lower())

    def comment_as_webhook_entity(self, issue_key, comment_id):
        return {
            "id": str(comment_id),
            "author": {"accountId": "human-1"},
            "updateAuthor": {"accountId": "human-1"},
        }

    def worklog_as_webhook_entity(self, issue_key, worklog_id):
        return {
            "id": str(worklog_id),
            "issueId": issue_key,
            "author": {"accountId": "human-1"},
            "updateAuthor": {"accountId": "human-1"},
        }


class NormalizeAutomationRequestTest(unittest.TestCase):
    def test_webhook_payload_passes_through(self):
        payload = {"webhookEvent": "jira:issue_updated", "changelog": {"items": []}}
        result = normalize_automation_request(payload, "issue", "KEY-1")
        self.assertEqual(result, payload)

    def test_issue_full_sync_without_trigger(self):
        jira = MockJira()
        result = normalize_automation_request(
            {
                "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                "actor": {"accountId": "user-1"},
            },
            "issue",
            "KEY-1",
            jira=jira,
        )
        self.assertEqual(result["changelog"]["items"][0]["fieldId"], "customfield_sync")
        self.assertEqual(result["user"]["accountId"], "user-1")

    def test_rejects_issue_triggers(self):
        jira = MockJira()
        for bad_trigger in ("issue.created", "issue.updated", "issue.field_changed"):
            with self.subTest(trigger=bad_trigger):
                with self.assertRaises(JiraAutomationPayloadError):
                    normalize_automation_request(
                        {
                            "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                            "trigger": bad_trigger,
                        },
                        "issue",
                        "KEY-1",
                        jira=jira,
                    )

    def test_minimal_automation_body_full_sync(self):
        jira = MockJira()
        result = normalize_automation_request(
            {
                "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                "user": {"accountId": "user-1"},
            },
            "issue",
            "KEY-1",
            jira=jira,
        )
        self.assertEqual(result["webhookEvent"], "jira:issue_updated")
        self.assertEqual(result["issue"], {"key": "KEY-1", "id": "10001"})
        self.assertEqual(result["user"], {"accountId": "user-1"})
        self.assertIn("changelog", result)

    def test_rejects_empty_field_change_from_blank_smart_values(self):
        with self.assertRaises(JiraAutomationPayloadError):
            normalize_automation_request(
                {
                    "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                    "field_change": {
                        "field": "",
                        "fieldId": "",
                        "fromString": "a",
                        "toString": "b",
                    },
                },
                "issue",
                "KEY-1",
            )

    def test_field_change_builds_changelog_with_value_strings(self):
        result = normalize_automation_request(
            {
                "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                "field_change": {
                    "field": "Summary",
                    "fieldId": "summary",
                    "fromString": "old title",
                    "toString": "new title",
                },
            },
            "issue",
            "KEY-1",
        )
        self.assertEqual(
            result["changelog"]["items"],
            [
                {
                    "field": "Summary",
                    "fieldId": "summary",
                    "fromString": "old title",
                    "toString": "new title",
                }
            ],
        )

    def test_sync_changed_only_rejected(self):
        jira = MockJira()
        with self.assertRaises(JiraAutomationPayloadError):
            normalize_automation_request(
                {
                    "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                    "sync_changed_only": True,
                },
                "issue",
                "KEY-1",
                jira=jira,
            )

    def test_issue_created_sets_full_sync(self):
        result = normalize_automation_request(
            {
                "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                "webhook_event": "jira:issue_created",
            },
            "issue",
            "KEY-1",
        )
        self.assertEqual(result["webhookEvent"], "jira:issue_created")
        self.assertIn("changelog", result)

    def test_rejects_unexpanded_smart_values(self):
        with self.assertRaises(JiraAutomationPayloadError):
            normalize_automation_request(
                {
                    "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                    "field_change": {"field": "{{fieldChange.field.name}}"},
                },
                "issue",
                "KEY-1",
            )

    def test_comment_string_shorthand(self):
        jira = MockJira()
        result = normalize_automation_request(
            {
                "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                "trigger": "comment.added",
                "comment": "5001",
            },
            "issue",
            "KEY-1",
            jira=jira,
        )
        self.assertEqual(result["comment"]["id"], "5001")

    def test_infers_issue_field_changed_from_field_change(self):
        result = normalize_automation_request(
            {
                "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                "field_change": {
                    "fieldId": "summary",
                    "fromString": "was",
                    "toString": "now",
                },
            },
            "issue",
            "KEY-1",
        )
        self.assertEqual(result["webhookEvent"], "jira:issue_updated")
        item = result["changelog"]["items"][0]
        self.assertEqual(item["fieldId"], "summary")
        self.assertEqual(item["fromString"], "was")
        self.assertEqual(item["toString"], "now")

    def test_comment_created_loads_comment(self):
        jira = MockJira()
        result = normalize_automation_request(
            {
                "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                "trigger": "comment.added",
                "comment_id": "5001",
            },
            "issue",
            "KEY-1",
            jira=jira,
        )
        self.assertEqual(result["webhookEvent"], "comment_created")
        self.assertEqual(result["comment"]["id"], "5001")
        self.assertEqual(result["comment"]["author"]["accountId"], "human-1")

    def test_comment_deleted_minimal_payload(self):
        result = normalize_automation_request(
            {
                "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                "webhook_event": "comment_deleted",
                "comment_id": "5001",
            },
            "issue",
            "KEY-1",
        )
        self.assertEqual(result["comment"], {"id": "5001"})

    def test_worklog_updated(self):
        jira = MockJira()
        result = normalize_automation_request(
            {
                "source": JIRA_PROJECT_AUTOMATION_SOURCE,
                "webhook_event": "worklog_updated",
                "worklog_id": "9001",
            },
            "issue",
            "KEY-1",
            jira=jira,
        )
        self.assertEqual(result["worklog"]["id"], "9001")
        self.assertEqual(result["worklog"]["issueId"], "KEY-1")


if __name__ == "__main__":
    unittest.main()
