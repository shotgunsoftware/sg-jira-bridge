# Copyright 2026 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

"""
Unit tests for the Jira Project Automation normalizer.

These tests only exercise :mod:`sg_jira.jira_automation_payload` against a fake
Jira, so they need neither Flow Production Tracking nor the Jira mocks. The tests
which send a normalized event through the Generic Syncer are in
``test_jira_automation_parity.py``.
"""

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

# The six ``{{eventType}}`` values of comment and worklog rules, with the kind
# of entity and the action each one stands for.
ENTITY_EVENTS = (
    ("comment_created", "comment", "created"),
    ("comment_updated", "comment", "updated"),
    ("comment_deleted", "comment", "deleted"),
    ("worklog_created", "worklog", "created"),
    ("worklog_updated", "worklog", "updated"),
    ("worklog_deleted", "worklog", "deleted"),
)


class FakeIssue:
    """The only parts of a Jira Issue the normalizer reads."""

    id = ISSUE_ID


class FakeJira:
    """
    Minimal stand-in for :class:`~sg_jira.jira_session.JiraSession`.

    It records how it was called, so tests can check that the normalizer only
    asks Jira for what it needs, and it can be told to fail.
    """

    def __init__(self):
        self.issue_calls = []
        self.loaded = []
        # What ``issue()`` raises, if anything.
        self.issue_error = None
        # The key Jira knows the Issue by, if it is to be returned.
        self.canonical_key = None
        # What ``get_jira_issue_field_id()`` answers for the Sync In FPTR field.
        self.sync_field_id = SYNC_FIELD_ID
        # What reading a comment or a worklog raises, if anything.
        self.entity_error = None

    def issue(self, key, **kwargs):
        """Return a fake Issue, or raise ``issue_error``."""
        self.issue_calls.append((key, kwargs))
        if self.issue_error:
            raise self.issue_error
        issue = FakeIssue()
        if self.canonical_key:
            issue.key = self.canonical_key
        return issue

    def get_jira_issue_field_id(self, name):
        """Return the id of the Sync In FPTR field, the only one known."""
        if name == JIRA_SYNC_IN_FPTR_FIELD.lower():
            return self.sync_field_id
        return None

    def comment_as_webhook_entity(self, issue_key, comment_id):
        """Return a comment, shaped like a webhook's ``comment`` block."""
        return self._load("comment", issue_key, comment_id, body="jira body")

    def worklog_as_webhook_entity(self, issue_key, worklog_id):
        """Return a worklog, shaped like a webhook's ``worklog`` block."""
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
    """
    Return an Issue full sync body, with ``overrides`` applied.

    :param overrides: Keys to add or replace. A value of ``None`` removes the key.
    """
    data = {"source": JIRA_PROJECT_AUTOMATION_SOURCE, "actor": dict(ACTOR)}
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


class TestAutomationPayloadBase(unittest.TestCase):
    """Common setup and helpers of the normalizer tests."""

    def setUp(self):
        """Test setup."""
        super().setUp()
        self.jira = FakeJira()

    def normalize(self, payload, resource_type="issue", resource_id="KEY-1"):
        """Normalize ``payload`` against the fake Jira."""
        return normalize_automation_request(
            payload, resource_type, resource_id, self.jira
        )

    def assert_rejected(self, payload, message=None, **kwargs):
        """
        Check that ``payload`` is refused as a bad request.

        :param str message: Text the error message must contain.
        """
        with self.assertRaises(JiraAutomationPayloadError) as ctx:
            self.normalize(payload, **kwargs)
        if message:
            self.assertIn(message, str(ctx.exception))


class TestIsAutomationRequest(unittest.TestCase):
    """Tell Project Automation bodies from site webhook bodies."""

    def test_is_automation_request_with_source(self):
        """Check that a body with the automation ``source`` is recognized."""
        self.assertTrue(is_automation_request(body()))

    def test_is_automation_request_site_webhook(self):
        """Check that a site webhook body is not an automation request."""
        self.assertFalse(is_automation_request({"webhookEvent": "jira:issue_updated"}))

    def test_is_automation_request_other_source(self):
        """Check that only the exact automation ``source`` is accepted."""
        for source in ("something_else", "JIRA_PROJECT_AUTOMATION", "", None):
            with self.subTest(source=source):
                self.assertFalse(is_automation_request({"source": source}))

    def test_is_automation_request_not_an_object(self):
        """Check that bodies which are not JSON objects are never automation."""
        for payload in (None, [], [body()], "text", 3):
            with self.subTest(payload=payload):
                self.assertFalse(is_automation_request(payload))


class TestNormalizeAutomationRequest(TestAutomationPayloadBase):
    """Request level checks, before the body is looked at."""

    def test_normalize_body_without_source_rejected(self):
        """Check that a site webhook body is refused by the normalizer."""
        self.assert_rejected({"webhookEvent": "jira:issue_updated"}, "source")

    def test_normalize_body_not_an_object_rejected(self):
        """Check that a body which is not a JSON object is refused."""
        for payload in (None, [], "text"):
            with self.subTest(payload=payload):
                self.assert_rejected(payload, "source")

    def test_normalize_resource_other_than_issue_rejected(self):
        """Check that only Issue resources can be synced with automation."""
        for resource_type in ("project", "comment", "", None):
            with self.subTest(resource_type=resource_type):
                self.assert_rejected(
                    body(), "Issue resources", resource_type=resource_type
                )

    def test_normalize_resource_type_case_insensitive(self):
        """Check that ``Issue`` and ``issue`` are the same resource type."""
        event = self.normalize(body(), resource_type="Issue")

        self.assertEqual(event["issue"]["id"], ISSUE_ID)

    def test_normalize_missing_issue_key_rejected(self):
        """Check that the Issue key is required in the request path."""
        for key in ("", None):
            with self.subTest(key=key):
                self.assert_rejected(body(), "Issue key", resource_id=key)

    def test_normalize_issue_key_used_as_given_when_jira_has_none(self):
        """Check that the Issue key of the path is kept if Jira gives no other."""
        event = self.normalize(body(), resource_id="key-7")

        self.assertEqual(event["issue"]["key"], "key-7")

    def test_normalize_issue_key_is_the_one_jira_knows(self):
        """
        Check that the key of the event is the one of Jira, as in a webhook.

        Test environment:
        - the path has the key in lower case, or the id of the Issue
        Expected result:
        - the event has the key as Jira writes it
        """
        self.jira.canonical_key = "KEY-7"
        for resource_id in ("key-7", ISSUE_ID):
            with self.subTest(resource_id=resource_id):
                event = self.normalize(body(), resource_id=resource_id)

                self.assertEqual(event["issue"], {"key": "KEY-7", "id": ISSUE_ID})

    def test_normalize_does_not_modify_payload(self):
        """
        Check that the request body is left as it was received.

        Expected result:
        - the body is equal to a copy taken before normalizing
        """
        payload = body(field_change={"fieldId": "summary"})
        snapshot = {**payload, "actor": dict(payload["actor"])}

        self.normalize(payload)

        self.assertEqual(payload, snapshot)

    def test_normalize_is_repeatable(self):
        """Check that the same body gives the same event each time it is sent."""
        payload = body(event_type="comment_created", id="5001")

        self.assertEqual(self.normalize(payload), self.normalize(payload))


class TestAutomationActor(TestAutomationPayloadBase):
    """
    The ``actor`` of a body, which becomes the ``user`` of the event.

    The syncer uses ``user`` to ignore the changes made by the bridge itself, so
    a rule must never reach it without one.
    """

    def test_actor_becomes_event_user(self):
        """Check that the actor of the rule is the user of the event."""
        self.assertEqual(self.normalize(body())["user"], {"accountId": "user-1"})

    def test_actor_reduced_to_account_id(self):
        """Check that nothing but the account id is forwarded."""
        event = self.normalize(body(actor={"accountId": "user-1", "name": "x"}))

        self.assertEqual(event["user"], {"accountId": "user-1"})

    def test_actor_missing_rejected(self):
        """Check that a body without ``actor`` is refused."""
        self.assert_rejected(body(actor=None), "actor is required")

    def test_actor_not_an_object_rejected(self):
        """Check that an ``actor`` which is not an object is refused."""
        for actor in ("user-1", ["user-1"], 1):
            with self.subTest(actor=actor):
                self.assert_rejected(body(actor=actor), "actor is required")

    def test_actor_blank_account_id_rejected(self):
        """
        Check that an empty account id is refused.

        Jira renders ``{{initiator.accountId}}`` empty when no user triggered the
        rule, for instance with a scheduled rule.
        """
        for account_id in ("", None):
            with self.subTest(account_id=account_id):
                self.assert_rejected(
                    body(actor={"accountId": account_id}), "actor.accountId is empty"
                )

    def test_actor_without_account_id_rejected(self):
        """Check that an ``actor`` with no account id is refused."""
        self.assert_rejected(body(actor={"name": "x"}), "actor.accountId is empty")

    def test_actor_required_for_every_kind_of_rule(self):
        """Check that comment and worklog rules need an ``actor`` as well."""
        for event_type, _, _ in ENTITY_EVENTS:
            with self.subTest(event_type=event_type):
                self.assert_rejected(
                    body(event_type=event_type, id="5001", actor=None),
                    "actor is required",
                )


class TestAutomationIssueLookup(TestAutomationPayloadBase):
    """The ``issue`` block of the event, read back from Jira."""

    def test_issue_reference_resolved_with_minimal_fields(self):
        """
        Check that only the id of the Issue is requested from Jira.

        Expected result:
        - one call to Jira, for the key of the path, asking for the ``id`` field
        """
        event = self.normalize(body(), resource_id="KEY-7")

        self.assertEqual(event["issue"], {"key": "KEY-7", "id": ISSUE_ID})
        self.assertEqual(self.jira.issue_calls, [("KEY-7", {"fields": "id"})])

    def test_issue_unknown_rejected(self):
        """Check that an Issue which does not exist is refused as a bad request."""
        self.jira.issue_error = JIRAError(status_code=404)

        self.assert_rejected(body(), "KEY-1")

    def test_issue_jira_errors_not_masked_as_bad_requests(self):
        """
        Check that Jira failing is not reported as a mistake in the rule.

        Expected result:
        - the Jira error is raised as is, so that it ends up as a server error
        """
        for status in (401, 403, 429, 500, 503):
            with self.subTest(status=status):
                self.jira.issue_error = JIRAError(status_code=status)
                with self.assertRaises(JIRAError):
                    self.normalize(body())

    def test_issue_read_before_the_entity(self):
        """Check that an unknown Issue is reported before any comment is read."""
        self.jira.issue_error = JIRAError(status_code=404)

        self.assert_rejected(body(event_type="comment_created", id="5001"), "KEY-1")

        self.assertEqual(self.jira.loaded, [])


class TestAutomationIssueFullSync(TestAutomationPayloadBase):
    """Issue rules which only send the ``actor``."""

    def test_full_sync_event(self):
        """
        Check the whole event built for a full sync.

        Expected result:
        - an Issue update event for the Issue of the path
        - whose changelog is a change of the Sync In FPTR field, which makes the
          handler sync every mapped field
        - carrying the actor as user
        """
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

    def test_full_sync_does_not_read_entities(self):
        """Check that an Issue rule never asks Jira for a comment or a worklog."""
        self.normalize(body())

        self.assertEqual(self.jira.loaded, [])

    def test_full_sync_missing_sync_field_fails_loudly(self):
        """
        Check that a Jira without the Sync In FPTR field is not hidden.

        Expected result:
        - a server error and not a bad request, as the rule is not at fault
        """
        self.jira.sync_field_id = None

        with self.assertRaises(RuntimeError):
            self.normalize(body())


class TestAutomationIssuePartialSync(TestAutomationPayloadBase):
    """Issue rules which send a ``field_change``."""

    def changelog_items(self, field_change):
        """Return the changelog items built for ``field_change``."""
        return self.normalize(body(field_change=field_change))["changelog"]["items"]

    def test_partial_sync_event(self):
        """
        Check the whole event built for a partial sync.

        Expected result:
        - an Issue update event, with one changelog item for the changed field
        - which keeps the values sent by the rule
        """
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

    def test_partial_sync_does_not_look_up_the_sync_field(self):
        """Check that a partial sync works whatever the Sync In FPTR field is."""
        self.jira.sync_field_id = None

        self.changelog_items({"fieldId": "summary"})

    def test_partial_sync_field_name_forwarded(self):
        """Check that the name of the field sent by the rule is kept."""
        items = self.changelog_items({"fieldId": "summary", "field": "Summary"})

        self.assertEqual(items, [{"field": "Summary", "fieldId": "summary"}])

    def test_partial_sync_field_name_defaults_to_field_id(self):
        """Check that the field id is used as name when the rule sends none."""
        for field_change in (
            {"fieldId": "summary"},
            {"fieldId": "summary", "field": ""},
        ):
            with self.subTest(field_change=field_change):
                self.assertEqual(
                    self.changelog_items(field_change),
                    [{"field": "summary", "fieldId": "summary"}],
                )

    def test_partial_sync_parent_change_keeps_its_field_name(self):
        """
        Check that a change of parent is named as the handler expects.

        The handler adds the parent to the fields to sync when the changed field
        is called ``IssueParentAssociation``, as it is in a site webhook.

        Expected result:
        - the changelog item has that name, whatever the field id
        """
        items = self.changelog_items(
            {"fieldId": "parent", "field": "IssueParentAssociation"}
        )

        self.assertEqual(
            items, [{"field": "IssueParentAssociation", "fieldId": "parent"}]
        )

    def test_partial_sync_cleared_value_kept(self):
        """
        Check that empty and null values are kept as they are.

        Jira sends an empty ``toString`` when a field is cleared.
        """
        for value in ("", None):
            with self.subTest(value=value):
                items = self.changelog_items(
                    {"fieldId": "summary", "fromString": "old", "toString": value}
                )
                self.assertEqual(items[0]["toString"], value)

    def test_partial_sync_field_id_missing_rejected(self):
        """Check that a ``field_change`` without a usable field id is refused."""
        for field_change in ({}, {"fieldId": ""}, {"field": "Summary"}):
            with self.subTest(field_change=field_change):
                self.assert_rejected(
                    body(field_change=field_change), "fieldId is required"
                )

    def test_partial_sync_not_an_object_rejected(self):
        """Check that a ``field_change`` which is not an object is refused."""
        for field_change in (None, "summary", ["summary"], []):
            with self.subTest(field_change=field_change):
                # Not body(): it drops None values.
                payload = {**body(), "field_change": field_change}
                self.assert_rejected(payload, "must be an object")

    def test_partial_sync_unknown_keys_rejected(self):
        """Check that a typo in the ``field_change`` is reported."""
        self.assert_rejected(
            body(field_change={"fieldId": "summary", "to": "x"}),
            "unexpected keys: to",
        )

    def test_partial_sync_does_not_read_entities(self):
        """Check that a partial sync never asks Jira for a comment or a worklog."""
        self.changelog_items({"fieldId": "summary"})

        self.assertEqual(self.jira.loaded, [])


class TestAutomationIssueRejectedKeys(TestAutomationPayloadBase):
    """Keys which Issue rules do not take."""

    def test_issue_unsupported_keys_rejected(self):
        """
        Check that every key which is not part of the contract is reported.

        Expected result:
        - a bad request naming the key, so that a typo in a rule is easy to find
        """
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
                self.assert_rejected(body(**{key: value}), f"unexpected keys: {key}")

    def test_issue_event_type_rejected(self):
        """Check that Issue rules take no ``event_type``."""
        for event_type in ("jira:issue_created", "issue_created"):
            with self.subTest(event_type=event_type):
                self.assert_rejected(
                    body(event_type=event_type), "Unsupported event_type"
                )

    def test_issue_blank_event_type_rejected(self):
        """
        Check that a blank ``event_type`` is not mistaken for a full sync.

        Expected result:
        - it is reported as an unexpected key
        """
        self.assert_rejected(body(event_type=""), "unexpected keys: event_type")

    def test_issue_blank_event_type_with_an_id_rejected(self):
        """Check that a comment rule whose ``event_type`` is empty is refused."""
        self.assert_rejected(
            body(event_type="", id="5001"), "unexpected keys: event_type, id"
        )


class TestAutomationEntityEvents(TestAutomationPayloadBase):
    """Comment and worklog rules, which send an ``event_type`` and an ``id``."""

    def entity_body(self, event_type="comment_created", **overrides):
        """Return a comment or worklog body, with ``overrides`` applied."""
        return body(**{"event_type": event_type, "id": "5001", **overrides})

    def test_entity_event_shaped_like_a_webhook(self):
        """
        Check the event built for each of the six comment and worklog events.

        Expected result:
        - the event is named like the webhook it replaces
        - it carries the Issue, the actor and the entity, and no changelog
        """
        for event_type, kind, _ in ENTITY_EVENTS:
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

    def test_entity_created_and_updated_read_from_jira(self):
        """Check that created and updated entities are read back from Jira."""
        for event_type, kind, action in ENTITY_EVENTS:
            if action == "deleted":
                continue
            with self.subTest(event_type=event_type):
                self.jira = FakeJira()

                event = self.normalize(self.entity_body(event_type))

                self.assertEqual(self.jira.loaded, [(kind, "KEY-1", "5001")])
                self.assertEqual(event[kind]["author"], {"accountId": "human-1"})
                self.assertEqual(event[kind]["updateAuthor"], {"accountId": "human-1"})

    def test_entity_deleted_not_read_from_jira(self):
        """
        Check that nothing is asked of Jira about something it no longer has.

        Expected result:
        - no comment or worklog is read
        """
        for event_type in ("comment_deleted", "worklog_deleted"):
            with self.subTest(event_type=event_type):
                self.jira = FakeJira()

                self.normalize(self.entity_body(event_type))

                self.assertEqual(self.jira.loaded, [])

    def test_entity_comment_deleted_only_carries_the_id(self):
        """Check that a deleted comment is as short as the webhook's."""
        event = self.normalize(self.entity_body("comment_deleted"))

        self.assertEqual(event["comment"], {"id": "5001"})

    def test_entity_worklog_deleted_carries_the_numeric_issue_id(self):
        """Check that a deleted worklog says which Issue it belonged to."""
        event = self.normalize(self.entity_body("worklog_deleted"))

        self.assertEqual(event["worklog"], {"id": "5001", "issueId": ISSUE_ID})

    def test_entity_event_type_case_insensitive(self):
        """Check that the case of ``{{eventType}}`` does not matter."""
        for event_type in ("Comment_Created", "COMMENT_CREATED"):
            with self.subTest(event_type=event_type):
                event = self.normalize(self.entity_body(event_type))

                self.assertEqual(event["webhookEvent"], "comment_created")

    def test_entity_id_not_a_string_or_integer_rejected(self):
        """Check that an id which is neither a string nor an integer is refused."""
        for entity_id in (["5001"], {"a": 1}, True, 1.5):
            with self.subTest(entity_id=entity_id):
                self.assert_rejected(
                    self.entity_body(id=entity_id), "id must be a string or an integer"
                )

    def test_entity_worklog_issue_id_is_numeric_for_every_action(self):
        """
        Check that a worklog always names its Issue by id, as a webhook does.

        Test environment:
        - what is read from Jira has the key of the Issue as ``issueId``
        Expected result:
        - the event has the numeric id of the Issue, created, updated or deleted
        """
        self.jira.worklog_as_webhook_entity = lambda key, worklog_id: {
            "id": str(worklog_id),
            "issueId": key,
            "author": {"accountId": "human-1"},
            "updateAuthor": {"accountId": "human-1"},
        }
        for event_type in ("worklog_created", "worklog_updated", "worklog_deleted"):
            with self.subTest(event_type=event_type):
                event = self.normalize(self.entity_body(event_type))

                self.assertEqual(event["worklog"]["issueId"], ISSUE_ID)

    def test_entity_comment_has_no_issue_id(self):
        """Check that only worklogs get an ``issueId``, as in a webhook."""
        event = self.normalize(self.entity_body("comment_created"))

        self.assertNotIn("issueId", event["comment"])

    def test_entity_integer_id_accepted(self):
        """Check that an id sent as a number is read like one sent as a string."""
        event = self.normalize(body(event_type="comment_created", id=5001))

        self.assertEqual(event["comment"]["id"], "5001")

    def test_entity_jira_data_wins_over_the_rule(self):
        """
        Check that the rule cannot change what Jira says about a comment.

        Expected result:
        - the body is the one read from Jira, not the one sent by the rule
        """
        event = self.normalize(self.entity_body(body="stale body"))

        self.assertEqual(event["comment"]["body"], "jira body")

    def test_entity_rule_data_kept_when_jira_has_none(self):
        """Check that what the rule sent completes what Jira does not provide."""
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

    def test_entity_deleted_keeps_rule_data(self):
        """Check that what the rule sent is all there is for a deleted comment."""
        event = self.normalize(self.entity_body("comment_deleted", body="gone"))

        self.assertEqual(event["comment"], {"id": "5001", "body": "gone"})

    def test_entity_comment_text_with_braces_kept(self):
        """Check that a comment which contains ``{{`` is not mistaken for an error."""
        text = "use {{curly}} braces"

        event = self.normalize(self.entity_body("comment_deleted", body=text))

        self.assertEqual(event["comment"]["body"], text)

    def test_entity_id_missing_rejected(self):
        """Check that a comment or worklog rule without an id is refused."""
        for entity_id in (None, ""):
            with self.subTest(entity_id=entity_id):
                self.assert_rejected(
                    body(event_type="comment_created", id=entity_id),
                    '"id": "{{comment.id}}"',
                )

    def test_entity_worklog_id_hint_names_the_worklog_smart_value(self):
        """Check that the error tells which smart value a worklog rule needs."""
        self.assert_rejected(
            body(event_type="worklog_created"), '"id": "{{worklog.id}}"'
        )

    def test_entity_unexpanded_id_not_found_in_jira(self):
        """
        Check that an id Jira could not fill in ends as a refused request.

        There is no check of the smart value itself: Jira has no such comment.
        """
        self.jira.entity_error = ValueError(
            "Jira Comment '{{comment.id}}' was not found on Issue 'KEY-1'."
        )

        self.assert_rejected(self.entity_body(id="{{comment.id}}"), "was not found")

    def test_entity_unexpanded_event_type_unsupported(self):
        """Check that an ``{{eventType}}`` Jira could not fill in is refused."""
        self.assert_rejected(
            self.entity_body("{{eventType}}"), "Unsupported event_type"
        )

    def test_entity_unsupported_event_type_lists_valid_values(self):
        """Check that the error tells which event types can be used."""
        for event_type in ("comment_added", "jira:issue_updated", "worklog"):
            with self.subTest(event_type=event_type):
                self.assert_rejected(self.entity_body(event_type), "comment_created")

    def test_entity_keys_of_the_other_entity_rejected(self):
        """Check that a comment rule cannot take worklog keys and vice versa."""
        for event_type, extra in (
            ("comment_created", {"timeSpent": "1h"}),
            ("comment_created", {"timeSpentSeconds": "60"}),
            ("comment_created", {"comment": "text"}),
            ("worklog_created", {"body": "text"}),
        ):
            with self.subTest(event_type=event_type, extra=extra):
                self.assert_rejected(
                    self.entity_body(event_type, **extra), "unexpected keys"
                )

    def test_entity_issue_and_legacy_keys_rejected(self):
        """Check that keys of Issue rules and of the former format are refused."""
        for key, value in (
            ("field_change", {"fieldId": "summary"}),
            ("comment_id", "5001"),
            ("worklog_id", "9001"),
            ("webhook_event", "comment_created"),
            ("eventType", "comment_created"),
            ("user", dict(ACTOR)),
        ):
            with self.subTest(key=key):
                self.assert_rejected(
                    self.entity_body(**{key: value}), f"unexpected keys: {key}"
                )

    def test_entity_missing_in_jira_rejected(self):
        """Check that a comment or worklog which does not exist is refused."""
        self.jira.entity_error = ValueError("Jira Comment '5001' was not found.")

        self.assert_rejected(self.entity_body(), "was not found")

    def test_entity_jira_errors_not_masked_as_bad_requests(self):
        """Check that Jira failing is raised as is, and not as a bad request."""
        self.jira.entity_error = JIRAError(status_code=500)

        with self.assertRaises(JIRAError):
            self.normalize(self.entity_body())


if __name__ == "__main__":
    unittest.main()
