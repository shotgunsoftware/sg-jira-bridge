# Copyright 2026 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import unittest

from jira import JIRAError

from sg_jira.constants import (
    JIRA_PROJECT_AUTOMATION_SOURCE,
    JIRA_SYNC_IN_FPTR_FIELD,
)
from sg_jira.jira_automation_payload import (
    JiraAutomationPayloadError,
    is_automation_request,
    normalize_automation_request,
)

SYNC_FIELD_ID = "customfield_sync"
ISSUE_ID = "10001"
ACTOR = {"accountId": "user-1"}


class FakeIssue:
    id = ISSUE_ID


class FakeJira:
    """Minimal stand-in for JiraSession, recording how it was called."""

    def __init__(self):
        self.issue_calls = []
        self.loaded = []
        self.issue_error = None
        self.sync_field_id = SYNC_FIELD_ID
        self.entity_error = None

    def issue(self, key, **kwargs):
        self.issue_calls.append((key, kwargs))
        if self.issue_error:
            raise self.issue_error
        return FakeIssue()

    def get_jira_issue_field_id(self, name):
        if name == JIRA_SYNC_IN_FPTR_FIELD.lower():
            return self.sync_field_id
        return None

    def comment_as_webhook_entity(self, issue_key, comment_id):
        return self._load("comment", issue_key, comment_id, body="jira body")

    def worklog_as_webhook_entity(self, issue_key, worklog_id):
        return self._load("worklog", issue_key, worklog_id, issueId=ISSUE_ID)

    def _load(self, kind, issue_key, entity_id, **extra):
        self.loaded.append((kind, issue_key, entity_id))
        if self.entity_error:
            raise self.entity_error
        return {
            "id": str(entity_id),
            "author": {"accountId": "human-1"},
            "updateAuthor": {"accountId": "human-1"},
            **extra,
        }


def body(**overrides):
    """An Issue full sync body, with ``overrides`` applied (None removes a key)."""
    data = {"source": JIRA_PROJECT_AUTOMATION_SOURCE, "actor": dict(ACTOR)}
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


class AutomationTestCase(unittest.TestCase):
    def setUp(self):
        self.jira = FakeJira()

    def normalize(self, payload, resource_type="issue", resource_id="KEY-1"):
        return normalize_automation_request(
            payload, resource_type, resource_id, self.jira
        )

    def assertRejected(self, payload, message=None, **kwargs):
        with self.assertRaises(JiraAutomationPayloadError) as ctx:
            self.normalize(payload, **kwargs)
        if message:
            self.assertIn(message, str(ctx.exception))


class IsAutomationRequestTest(unittest.TestCase):
    def test_detects_source(self):
        self.assertTrue(is_automation_request(body()))

    def test_site_webhook_is_not_automation(self):
        self.assertFalse(is_automation_request({"webhookEvent": "jira:issue_updated"}))

    def test_wrong_source_is_not_automation(self):
        self.assertFalse(is_automation_request({"source": "something_else"}))

    def test_non_dict_is_not_automation(self):
        for payload in (None, [], "text", 3):
            with self.subTest(payload=payload):
                self.assertFalse(is_automation_request(payload))


class RequestValidationTest(AutomationTestCase):
    def test_rejects_non_automation_body(self):
        self.assertRejected({"webhookEvent": "jira:issue_updated"}, "source")

    def test_rejects_non_issue_resource(self):
        self.assertRejected(body(), "Issue resources", resource_type="project")

    def test_resource_type_is_case_insensitive(self):
        self.assertEqual(
            self.normalize(body(), resource_type="Issue")["issue"]["id"], ISSUE_ID
        )

    def test_rejects_missing_issue_key(self):
        for key in ("", None):
            with self.subTest(key=key):
                self.assertRejected(body(), "Issue key", resource_id=key)

    def test_does_not_mutate_payload(self):
        payload = body(field_change={"fieldId": "summary"})
        snapshot = {**payload, "actor": dict(payload["actor"])}
        self.normalize(payload)
        self.assertEqual(payload, snapshot)


class ActorTest(AutomationTestCase):
    def test_actor_becomes_event_user(self):
        self.assertEqual(self.normalize(body())["user"], {"accountId": "user-1"})

    def test_actor_is_reduced_to_account_id(self):
        event = self.normalize(body(actor={"accountId": "user-1", "name": "x"}))
        self.assertEqual(event["user"], {"accountId": "user-1"})

    def test_actor_is_required(self):
        self.assertRejected(body(actor=None), "actor is required")

    def test_actor_must_be_object(self):
        for actor in ("user-1", ["user-1"], 1):
            with self.subTest(actor=actor):
                self.assertRejected(body(actor=actor), "actor is required")

    def test_blank_account_id_is_rejected(self):
        # Jira renders {{initiator.accountId}} empty when no user triggered the rule.
        for account_id in ("", None):
            with self.subTest(account_id=account_id):
                self.assertRejected(
                    body(actor={"accountId": account_id}), "actor.accountId is empty"
                )

    def test_missing_account_id_is_rejected(self):
        self.assertRejected(body(actor={"name": "x"}), "actor.accountId is empty")


class IssueLookupTest(AutomationTestCase):
    def test_issue_reference_resolves_id_with_minimal_fields(self):
        event = self.normalize(body(), resource_id="KEY-7")
        self.assertEqual(event["issue"], {"key": "KEY-7", "id": ISSUE_ID})
        self.assertEqual(self.jira.issue_calls, [("KEY-7", {"fields": "id"})])

    def test_unknown_issue_is_a_payload_error(self):
        self.jira.issue_error = JIRAError(status_code=404)
        self.assertRejected(body(), "KEY-1")

    def test_other_jira_errors_are_not_masked_as_bad_requests(self):
        for status in (401, 429, 500):
            with self.subTest(status=status):
                self.jira.issue_error = JIRAError(status_code=status)
                with self.assertRaises(JIRAError):
                    self.normalize(body())


class IssueFullSyncTest(AutomationTestCase):
    def test_full_sync_event(self):
        self.assertEqual(
            self.normalize(body()),
            {
                "webhookEvent": "jira:issue_updated",
                "issue": {"key": "KEY-1", "id": ISSUE_ID},
                "changelog": {
                    "items": [
                        {"field": JIRA_SYNC_IN_FPTR_FIELD, "fieldId": SYNC_FIELD_ID}
                    ]
                },
                "user": ACTOR,
            },
        )

    def test_missing_sync_field_fails_loudly(self):
        self.jira.sync_field_id = None
        with self.assertRaises(RuntimeError):
            self.normalize(body())


class IssuePartialSyncTest(AutomationTestCase):
    def changelog_items(self, field_change):
        return self.normalize(body(field_change=field_change))["changelog"]["items"]

    def test_partial_sync_event(self):
        event = self.normalize(
            body(
                field_change={
                    "fieldId": "summary",
                    "fromString": "old",
                    "toString": "new",
                }
            )
        )
        self.assertEqual(event["webhookEvent"], "jira:issue_updated")
        self.assertEqual(
            event["changelog"]["items"],
            [
                {
                    "field": "summary",
                    "fieldId": "summary",
                    "fromString": "old",
                    "toString": "new",
                }
            ],
        )

    def test_does_not_look_up_sync_field(self):
        self.jira.sync_field_id = None
        self.changelog_items({"fieldId": "summary"})

    def test_field_name_is_passed_through(self):
        items = self.changelog_items({"fieldId": "summary", "field": "Summary"})
        self.assertEqual(items[0]["field"], "Summary")

    def test_value_strings_are_optional(self):
        self.assertEqual(
            self.changelog_items({"fieldId": "summary"}),
            [{"field": "summary", "fieldId": "summary"}],
        )

    def test_cleared_value_is_kept(self):
        items = self.changelog_items(
            {"fieldId": "summary", "fromString": "old", "toString": ""}
        )
        self.assertEqual(items[0]["toString"], "")

    def test_field_id_is_required(self):
        for field_change in (
            {},
            {"fieldId": ""},
            {"field": "Summary"},
        ):
            with self.subTest(field_change=field_change):
                self.assertRejected(
                    body(field_change=field_change), "fieldId is required"
                )

    def test_field_change_must_be_object(self):
        for field_change in (None, "summary", ["summary"], []):
            with self.subTest(field_change=field_change):
                # Not body(): it drops None values.
                payload = {**body(), "field_change": field_change}
                self.assertRejected(payload, "must be an object")

    def test_unknown_field_change_keys_are_rejected(self):
        self.assertRejected(
            body(field_change={"fieldId": "summary", "to": "x"}), "unexpected keys: to"
        )


class EmptyEventTypeTest(AutomationTestCase):
    def test_empty_event_type_is_not_an_entity_rule(self):
        """A blank event_type is not a comment/worklog rule, and Issue rules
        take no event_type, so it is rejected as an unexpected key."""
        self.assertRejected(body(event_type=""), "unexpected keys: event_type")

    def test_empty_event_type_with_an_id_is_rejected(self):
        self.assertRejected(
            body(event_type="", id="5001"), "unexpected keys: event_type, id"
        )


class IssueRejectedKeysTest(AutomationTestCase):
    def test_unsupported_keys_are_rejected(self):
        for key, value in (
            ("user", dict(ACTOR)),
            ("webhook_event", "jira:issue_updated"),
            ("webhookEvent", "jira:issue_updated"),
            ("trigger", "comment.added"),
            ("changed_fields", [{"fieldId": "summary"}]),
            ("sync_changed_only", True),
            ("id", "5001"),
            ("comment_id", "5001"),
            ("body", "text"),
        ):
            with self.subTest(key=key):
                self.assertRejected(body(**{key: value}), f"unexpected keys: {key}")

    def test_issue_rules_do_not_take_an_event_type(self):
        for event_type in ("jira:issue_created", "issue_created"):
            with self.subTest(event_type=event_type):
                self.assertRejected(
                    body(event_type=event_type), "Unsupported event_type"
                )


ENTITY_EVENTS = (
    ("comment_created", "comment", "created"),
    ("comment_updated", "comment", "updated"),
    ("comment_deleted", "comment", "deleted"),
    ("worklog_created", "worklog", "created"),
    ("worklog_updated", "worklog", "updated"),
    ("worklog_deleted", "worklog", "deleted"),
)


class EntityEventTest(AutomationTestCase):
    def entity_body(self, event_type="comment_created", **overrides):
        return body(**{"event_type": event_type, "id": "5001", **overrides})

    def test_event_is_shaped_like_a_webhook(self):
        for event_type, kind, action in ENTITY_EVENTS:
            with self.subTest(event_type=event_type):
                self.jira = FakeJira()
                event = self.normalize(self.entity_body(event_type))
                self.assertEqual(event["webhookEvent"], event_type)
                self.assertEqual(event["issue"], {"key": "KEY-1", "id": ISSUE_ID})
                self.assertEqual(event["user"], ACTOR)
                self.assertEqual(event[kind]["id"], "5001")
                self.assertNotIn("changelog", event)
                other = "worklog" if kind == "comment" else "comment"
                self.assertNotIn(other, event)

    def test_created_and_updated_load_the_entity_from_jira(self):
        for event_type, kind, action in ENTITY_EVENTS:
            if action == "deleted":
                continue
            with self.subTest(event_type=event_type):
                self.jira = FakeJira()
                event = self.normalize(self.entity_body(event_type))
                self.assertEqual(self.jira.loaded, [(kind, "KEY-1", "5001")])
                self.assertEqual(event[kind]["author"], {"accountId": "human-1"})
                self.assertEqual(event[kind]["updateAuthor"], {"accountId": "human-1"})

    def test_deleted_does_not_call_jira_for_the_entity(self):
        for event_type in ("comment_deleted", "worklog_deleted"):
            with self.subTest(event_type=event_type):
                self.jira = FakeJira()
                self.normalize(self.entity_body(event_type))
                self.assertEqual(self.jira.loaded, [])

    def test_deleted_comment_only_carries_the_id(self):
        event = self.normalize(self.entity_body("comment_deleted"))
        self.assertEqual(event["comment"], {"id": "5001"})

    def test_deleted_worklog_carries_the_numeric_issue_id(self):
        event = self.normalize(self.entity_body("worklog_deleted"))
        self.assertEqual(event["worklog"], {"id": "5001", "issueId": ISSUE_ID})

    def test_event_type_is_case_insensitive(self):
        for event_type in ("Comment_Created", "COMMENT_CREATED"):
            with self.subTest(event_type=event_type):
                event = self.normalize(self.entity_body(event_type))
                self.assertEqual(event["webhookEvent"], "comment_created")

    def test_integer_id_is_accepted(self):
        event = self.normalize(body(event_type="comment_created", id=5001))
        self.assertEqual(event["comment"]["id"], "5001")

    def test_jira_data_wins_over_what_the_rule_sent(self):
        event = self.normalize(self.entity_body(body="stale body"))
        self.assertEqual(event["comment"]["body"], "jira body")

    def test_rule_data_is_kept_when_jira_has_nothing_to_say(self):
        event = self.normalize(
            self.entity_body(
                "worklog_updated",
                comment="2h on task",
                timeSpentSeconds="7200",
                timeSpent="2h",
            )
        )
        self.assertEqual(event["worklog"]["comment"], "2h on task")
        self.assertEqual(event["worklog"]["timeSpentSeconds"], "7200")
        self.assertEqual(event["worklog"]["timeSpent"], "2h")

    def test_deleted_keeps_rule_data(self):
        event = self.normalize(self.entity_body("comment_deleted", body="gone"))
        self.assertEqual(event["comment"], {"id": "5001", "body": "gone"})

    def test_comment_text_with_braces_is_not_a_smart_value(self):
        text = "use {{curly}} braces"
        event = self.normalize(self.entity_body("comment_deleted", body=text))
        self.assertEqual(event["comment"]["body"], text)

    def test_id_is_required(self):
        for entity_id in (None, ""):
            with self.subTest(entity_id=entity_id):
                self.assertRejected(
                    body(event_type="comment_created", id=entity_id),
                    '"id": "{{comment.id}}"',
                )

    def test_worklog_id_hint_names_the_worklog_smart_value(self):
        self.assertRejected(
            body(event_type="worklog_created"), '"id": "{{worklog.id}}"'
        )

    def test_unexpanded_id_is_not_found_in_jira(self):
        # No smart value check: Jira simply has no such comment.
        self.jira.entity_error = ValueError(
            "Jira Comment '{{comment.id}}' was not found on Issue 'KEY-1'."
        )
        self.assertRejected(self.entity_body(id="{{comment.id}}"), "was not found")

    def test_unexpanded_event_type_is_unsupported(self):
        self.assertRejected(self.entity_body("{{eventType}}"), "Unsupported event_type")

    def test_unsupported_event_type_lists_valid_values(self):
        for event_type in ("comment_added", "jira:issue_updated", "worklog"):
            with self.subTest(event_type=event_type):
                self.assertRejected(self.entity_body(event_type), "comment_created")

    def test_keys_of_the_other_entity_are_rejected(self):
        for event_type, extra in (
            ("comment_created", {"timeSpent": "1h"}),
            ("comment_created", {"timeSpentSeconds": "60"}),
            ("comment_created", {"comment": "text"}),
            ("worklog_created", {"body": "text"}),
        ):
            with self.subTest(event_type=event_type, extra=extra):
                self.assertRejected(
                    self.entity_body(event_type, **extra), "unexpected keys"
                )

    def test_issue_and_legacy_keys_are_rejected(self):
        for key, value in (
            ("field_change", {"fieldId": "summary"}),
            ("comment_id", "5001"),
            ("worklog_id", "9001"),
            ("webhook_event", "comment_created"),
            ("eventType", "comment_created"),
            ("user", dict(ACTOR)),
        ):
            with self.subTest(key=key):
                self.assertRejected(
                    self.entity_body(**{key: value}), f"unexpected keys: {key}"
                )

    def test_missing_entity_is_a_payload_error(self):
        self.jira.entity_error = ValueError("Jira Comment '5001' was not found.")
        self.assertRejected(self.entity_body(), "was not found")

    def test_unexpected_jira_errors_are_not_masked(self):
        self.jira.entity_error = JIRAError(status_code=500)
        with self.assertRaises(JIRAError):
            self.normalize(self.entity_body())


if __name__ == "__main__":
    unittest.main()
