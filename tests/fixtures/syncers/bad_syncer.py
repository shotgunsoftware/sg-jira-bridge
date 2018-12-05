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
    def __init__(self, fail_on_setup=True, **kwargs):
        """
        Instantiate a new syncer, collect the steps where a failure should happen.

        :param bool fail_on_setup: Whether this syncer should fail during setup.
        """
        super(BadSyncer, self).__init__(**kwargs)
        self._fail_on_setup = fail_on_setup

    def setup(self):
        """
        Raise RuntimeError if set to do it.
        """
        if self._fail_on_setup:
            raise RuntimeError("Sorry, I'm bad!")

