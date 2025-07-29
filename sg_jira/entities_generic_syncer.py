# Copyright 2024 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from .syncer import Syncer
from .handlers.entities_generic_handler import EntitiesGenericHandler


class EntitiesGenericSyncer(Syncer):
    """
    Sync Flow Production Tracking Entities as Jira Entities.
    This generic syncer relies on the settings.py file to define how the entities are synced, such as which entities
    and their fields mappings.
    """

    def __init__(self, entity_mapping=None, **kwargs):
        """
        Instantiate a new generic entities syncer for the given bridge.

        :param list entity_mapping: All the entities/fields mapping defined in the settings.
            This will be used to know what/how to sync entities between Flow Production Tracking and Jira.
        """

        # Call base class init with all parameters we do not handle specifically
        super().__init__(**kwargs)

        # we need one and only one handler here as everything will be handled within it
        self._entities_handler = EntitiesGenericHandler(
            self, entity_mapping if entity_mapping else []
        )

    @property
    def handlers(self):
        """Return a list of :class:`~handlers.SyncHandler` instances."""
        return [self._entities_handler]
