# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from sg_jira import Syncer
from .entities_handler import EntitiesHandler


class EntitiesSyncer(Syncer):
    """Sync Flow Production Tracking Entities as Jira Entities."""

    def __init__(self, entity_mapping=[], **kwargs):
        """Instantiate a new syncer with additional parameters from the base class"""

        # Call base class init with all parameters we do not handle specifically
        super(EntitiesSyncer, self).__init__(**kwargs)

        self._entities_handler = EntitiesHandler(self, entity_mapping)

    @property
    def handlers(self):
        """Return a list of :class:`~handlers.SyncHandler` instances."""
        return [self._entities_handler]