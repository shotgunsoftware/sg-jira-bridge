# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from sg_jira import Syncer
from sg_jira.handlers import TaskIssueHandler, NoteCommentHandler, EnableSyncingHandler
from .timelog_worklog_handler import TimelogWorklogHandler


class TimelogWorklogSyncer(Syncer):
    """Sync Flow Production Tracking Timelogs as Jira Worklogs."""

    def __init__(
        self,
        issue_type="Task",
        sync_sg_timelog_deletion=True,
        sync_jira_worklog_deletion=True,
        **kwargs
    ):
        """
        Instantiate a new syncer with additional parameters from the base class

        :param issue_type: Flow Production Tracking entity type associated to the Jira Issue
            (needed by the TaskIssueHandler)
        :param sync_sg_timelog_deletion: If True, when a worklog is deleted in Jira, it will also be deleted in Flow
            Production Tracking
        :param sync_jira_worklog_deletion: If True, when a timelog is deleted in Flow Production Tracking, it will also
            be deleted in Jira
        """
        # Call base class init with all parameters we do not handle specifically
        super().__init__(**kwargs)

        # Inherit from the other handlers to be able to perform the Task/Note sync as well as the Timelog sync
        self._task_issue_handler = TaskIssueHandler(self, issue_type)
        self._note_comment_handler = NoteCommentHandler(self)
        self._timelog_worklog_handler = TimelogWorklogHandler(
            self, sync_sg_timelog_deletion, sync_jira_worklog_deletion
        )

        # A handler combining the Task <-> Issue handler, the Note <-> Comment
        # handler and the TimeLog <-> Worklog handler. Task syncing to Jira starts
        # if the Task "Sync in Jira" checkbox is turned on. Notes linked to a Task
        # being actively synced are automatically synced without having to manually
        # select them, same for the TimeLogs. A full sync is performed when the
        # Task checkbox is turned on.
        self._enable_syncing_handler = EnableSyncingHandler(
            self,
            [
                self._task_issue_handler,
                self._note_comment_handler,
                self._timelog_worklog_handler,
            ],
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
            self._timelog_worklog_handler,
        ]
