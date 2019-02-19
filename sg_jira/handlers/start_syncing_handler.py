# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from ..constants import SHOTGUN_SYNC_IN_JIRA_FIELD
from .sync_handler import SyncHandler


class StartSyncingHandler(SyncHandler):
    """
    A handler which combines multiple handlers to perform an initial sync when
    a "Sync In Jira" checkbox field is changed in Shotgun.
    """

    def __init__(self, syncer, handlers):
        """
        Instantiate a new handler which combines the provided handlers.

        The first handler in the list is assumed to be a primary handler, the
        others are assumed to be secondary handlers.

        Events will be sent to secondary handlers for processing only if the
        primary handler was able to successfully process them.

        Combined handlers shouldn't accept the events which are accepted by this
        handler, but they need to be able to process them.

        :param syncer: A :class:`Syncer` instance.
        :param handlers: A non empty list of :class:`SyncHandler` instances.
        """
        super(StartSyncingHandler, self).__init__(syncer)
        if not handlers:
            raise ValueError("At least one handler needs to be provided")
        self._primary_handler = handlers[0]
        self._secondary_handlers = handlers[1:]

    def setup(self):
        """
        Check the Jira and Shotgun site, ensure that the sync can safely happen.
        This can be used as well to cache any value which is slow to retrieve.

        Run all handlers setup.
        """
        self._primary_handler.setup()
        for handler in self._secondary_handlers:
            handler.setup()

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :returns: `True` if the event is accepted for processing, `False` otherwise.
        """
        meta = event["meta"]
        field = meta["attribute_name"]

        if field == SHOTGUN_SYNC_IN_JIRA_FIELD:
            # Check the value which was set
            return bool(meta["new_value"])

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Shotgun event for the given Shotgun Entity

        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event for the change.
        """
        # Run the primary handler, stop processing if the primary handler
        # didn't perform anything.
        self._logger.debug(
            "Dispatching event %s to primary handler %s" % (
                event,
                self._primary_handler
            )
        )
        if not self._primary_handler.process_shotgun_event(
            entity_type,
            entity_id,
            event,
        ):
            return False

        # Run all the secondary handlers
        for handler in self._secondary_handlers:
            self._logger.debug(
                "Dispatching event %s to secondary handler %s" % (
                    event,
                    handler
                )
            )
            handler.process_shotgun_event(
                entity_type,
                entity_id,
                event,
            )
        return True

    def accept_jira_event(self, resource_type, resource_id, event):
        """
        Accept or reject the given event for the given Jira resource.

        This handler rejects all Jira events.

        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event is accepted for processing, False otherwise.
        """
        return False
