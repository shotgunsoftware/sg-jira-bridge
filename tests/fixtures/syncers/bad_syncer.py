# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from sg_jira import Syncer


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
        self._fail_on_sg_sync = fail_on_sg_sync

    def setup(self):
        """
        Raise RuntimeError if set to do it.
        """
        if self._fail_on_setup:
            raise RuntimeError("Sorry, I'm bad!")
        return super(BadSyncer, self).setup()

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Raise RuntimeError if set to do it.
        """
        if self._fail_on_sg_accept:
            raise RuntimeError("Sorry, I'm bad!")
        return super(BadSyncer, self).accept_shotgun_event(entity_type, entity_id, event)

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Raise RuntimeError if set to do it.
        """
        if self._fail_on_sg_sync:
            raise RuntimeError("Sorry, I'm bad!")
        return super(BadSyncer, self).process_shotgun_event(entity_type, entity_id, event)
