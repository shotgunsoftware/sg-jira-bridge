# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from ..constants import SHOTGUN_SYNC_IN_JIRA_FIELD
from .sync_handler import SyncHandler


class EnableSyncingHandler(SyncHandler):
    """
    A handler which combines multiple handlers to start syncing Tasks and Entities
    linked to them when a Task "Sync In Jira" (sg_sync_in_jira) checkbox field
    is changed in Shotgun.

    A full sync is performed each time the checkbox is turned on. This allows
    to manually force a re-sync if needed by just setting off the checkbox, and
    then back to on.
    """

    def __init__(self, syncer, handlers):
        """
        Instantiate a new handler which combines the provided handlers.

        The first handler in the list is assumed to be a primary handler, the
        others are assumed to be secondary handlers.

        Events will be sent to secondary handlers for processing only if the
        primary handler was able to successfully process them.

        This allows to control from the primary handler if a Shotgun Entity should
        be synced or not, and then automatically start syncing secondary Entities
        which are linked to this primary Entity, e.g. Notes on a Task, without
        having to explicitely enable syncing for the linked Entities.

        Combined handlers shouldn't accept the events which are accepted by this
        handler, but they need to be able to process them.

        :param syncer: A :class:`~sg_jira.Syncer` instance.
        :param handlers: A non empty list of :class:`SyncHandler` instances.
        """
        super(EnableSyncingHandler, self).__init__(syncer)
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

        # We only accept Tasks
        if entity_type != "Task":
            return False

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
            "Dispatching event to primary handler %s. Event: %s"
            % (self._primary_handler, event)
        )
        if not self._primary_handler.process_shotgun_event(
            entity_type, entity_id, event,
        ):
            return False

        # Run all the secondary handlers
        for handler in self._secondary_handlers:
            self._logger.debug(
                "Dispatching event to secondary handler %s. Event: %s"
                % (handler, event)
            )
            handler.process_shotgun_event(
                entity_type, entity_id, event,
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
