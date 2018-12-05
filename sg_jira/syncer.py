# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import logging

from .constants import JIRA_SHOTGUN_TYPE_FIELD, JIRA_SHOTGUN_ID_FIELD


class Syncer(object):
    """
    A class handling syncing between Shotgun and Jira
    """

    def __init__(self, name, bridge, **kwargs):
        """
        Instatiate a new syncer for the given bridge.

        :param str name: A unique name for the syncer.
        :param bridge: A :class:`sg_jira.Bridge` instance.
        """
        super(Syncer, self).__init__()
        self._name = name
        self._bridge = bridge
        # Set a logger per instance: this allows to filter logs with the
        # syncer name, or even have log file handlers per syncer
        self._logger = logging.getLogger(__name__).getChild(self._name)

    @property
    def logger(self):
        """
        Returns the logger used by this syncer.
        """
        return self._logger

    def setup(self):
        """
        Check the Jira and Shotgun site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """
        pass

    def match_jira_ressource(self, entity_type, entity_id, name):
        """
        Return a matching Jira resource for the given Shotgun Entity, if any.

        This base implementation matches resources by name and only handles Projects
        and mapping a Shotgun Task to a Jira Issue

        :param str entity_type: A Shotgun Entity type.
        :param int entity_id: A Shotgun Entity id.
        :param str name: A name to match, typically the Shotgun Entity name.
        """
        if entity_type == "Project":
            for jira_project in self._bridge.jira.projects():
                if jira_project.name.lower() == name.lower():
                    return jira_project

        elif entity_type == "Task":
            pass
        else:
            raise ValueError("Unsupported Entity type %s" % entity_type)

        return None

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :returns: True if the event is accepted for processing, False otherwise.
        """

        if not event:
            return False

        # Check we have a Project
        if not event.get("project"):
            self._logger.debug("Rejecting event %s with no project." % event)
            return False

        # Check we didn't trigger the event to avoid infinite loops.
        user = event.get("user")
        current_user = self._bridge.current_shotgun_user
        if user and current_user:
            if user["type"] == current_user["type"] and user["id"] == current_user["id"]:
                self._logger.debug("Rejecting event %s created by us." % event)
                return False

        return True

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Shotgun event for the given Shotgun Entity

        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event meta data for the change.
        """
        self._logger.info("Syncing in Jira %s(%d) for event %s" % (
            entity_type,
            entity_id,
            event
        ))

    def accept_jira_event(self, resource_type, resource_id, event):
        """
        TBD: could be used to implement special logic to ignore some events
        """
        return True

    def process_jira_event(self, resource_type, resource_id, event):
        """
        Process the given Jira event for the given Jira resource.

        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        """
        self._logger.info("Syncing in SG %s(%s) for event %s" % (
            resource_type,
            resource_id,
            event
        ))

