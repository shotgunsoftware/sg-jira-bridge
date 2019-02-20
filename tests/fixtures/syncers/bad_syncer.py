# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from sg_jira import Syncer
from sg_jira.handlers import SyncHandler


class BadHandler(SyncHandler):
    """
    A syncer handler which causes problems which should be handled gracefully.
    """
    def __init__(self, syncer, fail_on_sg_sync):
        """
        :param bool fail_on_sg_sync: Whether this syncer should fail when processing
                                     Shotgun events.
        """
        self._fail_on_sg_sync = fail_on_sg_sync
        return super(BadHandler, self).__init__(syncer)

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Raise RuntimeError if set to do it.
        """
        if self._fail_on_sg_sync:
            raise RuntimeError("Sorry, I'm bad!")
        return super(BadHandler, self).process_shotgun_event(entity_type, entity_id, event)


class BadSyncer(Syncer):
    """
    A syncer which causes problems which should be handled gracefully.
    """
    def __init__(
        self,
        fail_on_setup=False,
        fail_on_sg_accept=False,
        fail_on_sg_sync=False,
        **kwargs
    ):
        """
        Instantiate a new syncer, collect the steps where a failure should happen.

        :param bool fail_on_setup: Whether this syncer should fail during setup.
        :param bool fail_on_sg_accept: Whether this syncer should fail when accepting
                                       Shotgun events.
        :param bool fail_on_sg_sync: Whether this syncer should fail when processing
                                     Shotgun events.
        """
        super(BadSyncer, self).__init__(**kwargs)
        self._fail_on_setup = fail_on_setup
        self._fail_on_sg_accept = fail_on_sg_accept
        self._handler = BadHandler(self, fail_on_sg_sync)

    def setup(self):
        """
        Raise RuntimeError if set to do it.
        """
        if self._fail_on_setup:
            raise RuntimeError("Sorry, I'm bad!")
        return super(BadSyncer, self).setup()

    @property
    def handlers(self):
        return [self._handler]

    @property
    def sg_jira_statuses_mapping(self):
        return {}

    def supported_shotgun_fields(self, shotgun_entity_type):
        return ["sg_status_list"]

    def get_jira_issue_field_for_shotgun_field(self, shotgun_entity_type, shotgun_field):
        return None

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Raise RuntimeError if set to do it.
        """
        if self._fail_on_sg_accept:
            raise RuntimeError("Sorry, I'm bad!")
        return self._handler
