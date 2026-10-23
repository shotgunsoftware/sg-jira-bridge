# Copyright 2026 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import unittest
from unittest import mock

from jira import JIRAError

from sg_jira.jira_session import JiraSession


def user(account_id):
    return mock.Mock(
        spec=["accountId", "displayName"],
        accountId=account_id,
        displayName=f"name of {account_id}",
    )


class WebhookEntityTest(unittest.TestCase):
    """``comment_as_webhook_entity`` / ``worklog_as_webhook_entity`` shaping."""

    def setUp(self):
        # Skip connecting to Jira: only the methods under test are used.
        self.session = object.__new__(JiraSession)

    def patch(self, name, **kwargs):
        patcher = mock.patch.object(JiraSession, name, create=True, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_comment_has_the_keys_a_webhook_has(self):
        comment = mock.Mock(
            id=5001,
            body="hello",
            author=user("a"),
            updateAuthor=user("b"),
            spec=["id", "body", "author", "updateAuthor"],
        )
        self.patch("comment", return_value=comment)

        entity = self.session.comment_as_webhook_entity("KEY-1", "5001")

        self.assertEqual(
            entity,
            {
                "id": "5001",
                "body": "hello",
                "author": {"accountId": "a", "displayName": "name of a"},
                "updateAuthor": {"accountId": "b", "displayName": "name of b"},
            },
        )
        self.session.comment.assert_called_once_with("KEY-1", "5001")

    def test_comment_reply_keeps_its_parent(self):
        comment = mock.Mock(id=5002, body="re", author=user("a"), parentId="5001")
        self.patch("comment", return_value=comment)

        entity = self.session.comment_as_webhook_entity("KEY-1", "5002")

        self.assertEqual(entity["parentId"], "5001")

    def test_comment_update_author_falls_back_to_author(self):
        comment = mock.Mock(
            spec=["id", "body", "author"], id=1, body="", author=user("a")
        )
        self.patch("comment", return_value=comment)

        entity = self.session.comment_as_webhook_entity("KEY-1", "1")

        self.assertEqual(entity["updateAuthor"], entity["author"])

    def test_worklog_uses_the_numeric_issue_id(self):
        worklog = mock.Mock(
            spec=["id", "issue", "author"],
            id=9001,
            issue=mock.Mock(id=10001),
            author=user("a"),
        )
        self.patch("worklog", return_value=worklog)

        entity = self.session.worklog_as_webhook_entity("KEY-1", "9001")

        self.assertEqual(entity["id"], "9001")
        self.assertEqual(entity["issueId"], "10001")
        self.assertEqual(entity["updateAuthor"], entity["author"])

    def test_worklog_without_issue_falls_back_to_the_key(self):
        worklog = mock.Mock(spec=["id", "author"], id=9001, author=user("a"))
        self.patch("worklog", return_value=worklog)

        entity = self.session.worklog_as_webhook_entity("KEY-1", "9001")

        self.assertEqual(entity["issueId"], "KEY-1")

    def test_missing_resource_raises_value_error(self):
        # The Jira library raises a 404, some wrappers return None.
        for kind, loader in (
            ("comment", "comment_as_webhook_entity"),
            ("worklog", "worklog_as_webhook_entity"),
        ):
            for outcome in (
                {"side_effect": JIRAError(status_code=404)},
                {"return_value": None},
            ):
                with self.subTest(kind=kind, outcome=outcome):
                    self.patch(kind, **outcome)
                    with self.assertRaisesRegex(ValueError, "was not found"):
                        getattr(self.session, loader)("KEY-1", "1")

    def test_other_jira_errors_propagate(self):
        for kind, loader in (
            ("comment", "comment_as_webhook_entity"),
            ("worklog", "worklog_as_webhook_entity"),
        ):
            with self.subTest(kind=kind):
                self.patch(kind, side_effect=JIRAError(status_code=500))
                with self.assertRaises(JIRAError):
                    getattr(self.session, loader)("KEY-1", "1")

    def test_user_without_details_is_an_empty_dict(self):
        self.assertEqual(JiraSession._jira_user_to_webhook_dict(None), {})


if __name__ == "__main__":
    unittest.main()
