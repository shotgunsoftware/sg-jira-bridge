# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from .syncer import Syncer
from .constants import SHOTGUN_JIRA_ID_FIELD
from .handlers import TaskIssueHandler, NoteCommentHandler


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

    @property
    def handlers(self):
        """
        Return a list of :class:`SyncHandler` instances.
        """
        return [
            TaskIssueHandler(self, self._issue_type),
            NoteCommentHandler(self)
        ]
