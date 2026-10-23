# Copyright 2026 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

"""
Tests for the :class:`~sg_jira.jira_session.JiraSession` methods which read a
comment or a worklog back from Jira, shaped like a webhook payload.

Jira Project Automation only sends the id of a comment or worklog. The Generic
Syncer reads the rest, such as the author, from the event, as a site webhook
carries it, so these methods rebuild it.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from jira import JIRAError
from jira.resources import Comment, Worklog

from sg_jira.jira_session import JiraSession

# The two methods under test, with the Jira session method each one calls.
LOADERS = (
    ("comment", "comment_as_webhook_entity"),
    ("worklog", "worklog_as_webhook_entity"),
)


def jira_user(account_id, **attributes):
    """
    Return a Jira user, as the Jira library does for an author.

    :param str account_id: The ``accountId`` of the user.
    :param attributes: Any other attribute the user has.
    """
    return mock.Mock(
        spec=["accountId", *attributes], accountId=account_id, **attributes
    )


class TestJiraSessionWebhookEntities(unittest.TestCase):
    """Comments and worklogs read from Jira, shaped like webhook payloads."""

    def setUp(self):
        """Test setup."""
        super().setUp()
        # Skip connecting to Jira: only the methods under test are used.
        self.session = object.__new__(JiraSession)

    def patch_session(self, name, **kwargs):
        """Replace the ``name`` method of the Jira session for this test."""
        patcher = mock.patch.object(JiraSession, name, create=True, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    # -------------------------------------------------------------------------------
    # Comments
    # -------------------------------------------------------------------------------

    def test_comment_as_webhook_entity_has_webhook_keys(self):
        """
        Check that a comment has the keys of a ``comment_*`` webhook payload.

        Expected result:
        - the id as a string, the body, the author and the update author
        - the comment is read for the Issue and comment ids which were given
        """
        comment = mock.Mock(
            id=5001,
            body="hello",
            author=jira_user("a", displayName="Ann"),
            updateAuthor=jira_user("b", emailAddress="b@x.com"),
            spec=["id", "body", "author", "updateAuthor"],
        )
        self.patch_session("comment", return_value=comment)

        entity = self.session.comment_as_webhook_entity("KEY-1", "5001")

        self.assertEqual(
            entity,
            {
                "id": "5001",
                "body": "hello",
                "author": {"accountId": "a", "displayName": "Ann"},
                "updateAuthor": {"accountId": "b", "emailAddress": "b@x.com"},
            },
        )
        self.session.comment.assert_called_once_with("KEY-1", "5001")

    def test_comment_as_webhook_entity_reply_keeps_parent(self):
        """Check that the parent of a reply is kept, as reply sync routes on it."""
        comment = mock.Mock(id=5002, body="re", author=jira_user("a"), parentId="5001")
        self.patch_session("comment", return_value=comment)

        entity = self.session.comment_as_webhook_entity("KEY-1", "5002")

        self.assertEqual(entity["parentId"], "5001")

    def test_comment_as_webhook_entity_top_level_comment_has_no_parent(self):
        """Check that a comment which is not a reply has no ``parentId`` key."""
        comment = mock.Mock(
            spec=["id", "body", "author"], id=1, body="", author=jira_user("a")
        )
        self.patch_session("comment", return_value=comment)

        entity = self.session.comment_as_webhook_entity("KEY-1", "1")

        self.assertNotIn("parentId", entity)

    def test_comment_as_webhook_entity_update_author_falls_back_to_author(self):
        """Check that a comment never edited has its author as update author."""
        comment = mock.Mock(
            spec=["id", "body", "author"], id=1, body="", author=jira_user("a")
        )
        self.patch_session("comment", return_value=comment)

        entity = self.session.comment_as_webhook_entity("KEY-1", "1")

        self.assertEqual(entity["updateAuthor"], entity["author"])

    def test_comment_as_webhook_entity_without_body(self):
        """Check that a comment which has no body gets an empty one."""
        comment = mock.Mock(spec=["id", "author"], id=1, author=jira_user("a"))
        self.patch_session("comment", return_value=comment)

        entity = self.session.comment_as_webhook_entity("KEY-1", "1")

        self.assertEqual(entity["body"], "")

    # -------------------------------------------------------------------------------
    # Worklogs
    # -------------------------------------------------------------------------------

    def test_worklog_as_webhook_entity_has_webhook_keys(self):
        """
        Check that a worklog has the keys of a ``worklog_*`` webhook payload.

        Expected result:
        - the id as a string and the numeric id of its Issue
        - the author, and the author as update author
        """
        worklog = mock.Mock(
            spec=["id", "issueId", "author"],
            id=9001,
            issueId="10001",
            author=jira_user("a"),
        )
        self.patch_session("worklog", return_value=worklog)

        entity = self.session.worklog_as_webhook_entity("KEY-1", "9001")

        self.assertEqual(entity["id"], "9001")
        self.assertEqual(entity["issueId"], "10001")
        self.assertEqual(entity["author"], {"accountId": "a"})
        self.assertEqual(entity["updateAuthor"], entity["author"])
        self.session.worklog.assert_called_once_with("KEY-1", "9001")

    def test_worklog_as_webhook_entity_real_resource(self):
        """
        Check a worklog as the Jira library builds it from a REST response.

        The resource has the id of the Issue as ``issueId`` and has no ``issue``.
        Mocks which only have the attributes the code reads would hide it, so this
        one is built from the raw response of Jira.
        """
        worklog = Worklog(
            {},
            None,
            raw={
                "id": "9001",
                "issueId": "10001",
                "author": {"accountId": "a", "displayName": "Ann"},
                "timeSpentSeconds": 3600,
            },
        )
        self.patch_session("worklog", return_value=worklog)

        entity = self.session.worklog_as_webhook_entity("KEY-1", "9001")

        self.assertEqual(entity["issueId"], "10001")
        self.assertEqual(entity["author"], {"accountId": "a", "displayName": "Ann"})

    def test_comment_as_webhook_entity_real_resource(self):
        """
        Check a reply as the Jira library builds it from a REST response.

        Expected result:
        - the parent of the reply is read, as reply sync routes on it
        """
        comment = Comment(
            {},
            None,
            raw={
                "id": "5002",
                "body": "a reply",
                "parentId": "5001",
                "author": {"accountId": "a"},
            },
        )
        self.patch_session("comment", return_value=comment)

        entity = self.session.comment_as_webhook_entity("KEY-1", "5002")

        self.assertEqual(entity["parentId"], "5001")
        self.assertEqual(entity["body"], "a reply")

    def test_worklog_as_webhook_entity_without_issue_id_uses_issue_key(self):
        """Check that the key of the Issue is used when the worklog has no id of it."""
        worklog = mock.Mock(spec=["id", "author"], id=9001, author=jira_user("a"))
        self.patch_session("worklog", return_value=worklog)

        entity = self.session.worklog_as_webhook_entity("KEY-1", "9001")

        self.assertEqual(entity["issueId"], "KEY-1")

    # -------------------------------------------------------------------------------
    # Errors
    # -------------------------------------------------------------------------------

    def test_as_webhook_entity_missing_resource_raises_value_error(self):
        """
        Check that a comment or worklog which does not exist is reported alike.

        The Jira library raises a 404, some wrappers return None.

        Expected result:
        - a ``ValueError`` saying which resource was not found
        """
        for kind, loader in LOADERS:
            for outcome in (
                {"side_effect": JIRAError(status_code=404)},
                {"return_value": None},
            ):
                with self.subTest(kind=kind, outcome=outcome):
                    self.patch_session(kind, **outcome)

                    with self.assertRaisesRegex(ValueError, "was not found"):
                        getattr(self.session, loader)("KEY-1", "1")

    def test_as_webhook_entity_missing_resource_message_names_it(self):
        """Check that the error tells which resource and which Issue."""
        for kind, loader in LOADERS:
            with self.subTest(kind=kind):
                self.patch_session(kind, side_effect=JIRAError(status_code=404))

                with self.assertRaises(ValueError) as ctx:
                    getattr(self.session, loader)("KEY-1", "42")

                self.assertIn(kind.capitalize(), str(ctx.exception))
                self.assertIn("'42'", str(ctx.exception))
                self.assertIn("'KEY-1'", str(ctx.exception))

    def test_as_webhook_entity_other_jira_errors_propagate(self):
        """
        Check that Jira failing is not reported as a resource which is missing.

        Expected result:
        - the Jira error is raised as is, so that it can be told from a bad request
        """
        for kind, loader in LOADERS:
            for status in (401, 403, 429, 500, 503):
                with self.subTest(kind=kind, status=status):
                    self.patch_session(kind, side_effect=JIRAError(status_code=status))

                    with self.assertRaises(JIRAError):
                        getattr(self.session, loader)("KEY-1", "1")

    # -------------------------------------------------------------------------------
    # Users
    # -------------------------------------------------------------------------------

    def test_jira_user_to_webhook_dict_none(self):
        """Check that a missing user gives an empty dict, and not an error."""
        self.assertEqual(JiraSession._jira_user_to_webhook_dict(None), {})

    def test_jira_user_to_webhook_dict_keeps_known_attributes_only(self):
        """
        Check that only the attributes a webhook carries for a user are kept.

        Expected result:
        - account id, name, key, email address and display name
        - nothing else, such as the avatar urls
        """
        user = SimpleNamespace(
            accountId="a",
            name="ann",
            key="ann-key",
            emailAddress="a@x.com",
            displayName="Ann",
            avatarUrls={"48x48": "http://x"},
            active=True,
        )

        self.assertEqual(
            JiraSession._jira_user_to_webhook_dict(user),
            {
                "accountId": "a",
                "name": "ann",
                "key": "ann-key",
                "emailAddress": "a@x.com",
                "displayName": "Ann",
            },
        )

    def test_jira_user_to_webhook_dict_skips_missing_and_empty_attributes(self):
        """Check that attributes the user does not have, or has empty, are left out."""
        user = jira_user("a", emailAddress="", displayName=None)

        self.assertEqual(
            JiraSession._jira_user_to_webhook_dict(user), {"accountId": "a"}
        )


if __name__ == "__main__":
    unittest.main()
