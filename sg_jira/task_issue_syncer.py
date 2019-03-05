# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from .syncer import Syncer
from .handlers import TaskIssueHandler, NoteCommentHandler, EnableSyncingHandler


class TaskIssueSyncer(Syncer):
    """
    Sync Shotgun Tasks as Jira Issues.
    """
    def __init__(self, issue_type="Task", **kwargs):
        """
        Instatiate a new Task/Issue syncer for the given bridge.

        :param str issue_type: Jira Issue type to use when creating new Issues.
        """
        self._issue_type = issue_type
        super(TaskIssueSyncer, self).__init__(**kwargs)
        self._task_issue_handler = TaskIssueHandler(self, self._issue_type)
        self._note_comment_handler = NoteCommentHandler(self)
        # A handler combining the Task <-> Issue handler and the Note <-> Comment
        # handler. Task syncing to Jira starts if the Task "Sync in Jira" checkbox
        # is turned on. Notes linked to a Task being actively synced are automatically
        # synced without having to manually select them. A full sync is performed
        # when the Task checkbox is turned on.
        self._enable_syncing_handler = EnableSyncingHandler(
            self,
            [self._task_issue_handler, self._note_comment_handler]
        )

    @property
    def handlers(self):
        """
        Return a list of :class:`~handlers.SyncHandler` instances.
        """
        return [
            self._enable_syncing_handler,
            self._task_issue_handler,
            self._note_comment_handler
        ]
