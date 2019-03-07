# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from sg_jira import Syncer
from sg_jira.handlers import TaskIssueHandler, NoteCommentHandler, EnableSyncingHandler
from .asset_issue_handler import AssetIssueHandler


class AssetHierarchySyncer(Syncer):
    """
    Syncer example which mimics a simple Shotgun Asset/Task hierarchy in Jira .
    - Assets are synced as Jira Stories.
    - Tasks are synced as Jira Issues, with a dependency to the Asset Story.

    This example shows how you can combine handlers to provide your own logic
    and how you can re-use the existing handlers and base classes.
    """

    def __init__(self, asset_issue_type="Story", task_issue_type="Task", **kwargs):
        super(AssetHierarchySyncer, self).__init__(**kwargs)
        self._task_issue_handler = TaskIssueHandler(self, task_issue_type)
        self._note_comment_handler = NoteCommentHandler(self)
        self._asset_issue_handler = AssetIssueHandler(self, asset_issue_type)
        # A handler combining the Task <-> Issue handler and the Note <-> Comment
        # handler. Task syncing to Jira starts if the Task "Sync in Jira" checkbox
        # is turned on. Notes linked to a Task being actively synced are automatically
        # synced without having to manually select them. A full sync is performed
        # when the Task checkbox is turned on.
        self._enable_syncing_handler = EnableSyncingHandler(
            self, [
                self._task_issue_handler,
                self._asset_issue_handler,
                self._note_comment_handler
            ]
        )

    @property
    def handlers(self):
        """
        Return a list of :class:`~handlers.SyncHandler` instances.
        """
        return [
            self._enable_syncing_handler,
            self._task_issue_handler,
            self._note_comment_handler,
            self._asset_issue_handler
        ]
