# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#


class SyncHandler(object):
    """
    Base class to handle a particular sync between Shotgun and Jira.
    """

    def __init__(self, syncer):
        """
        """
        self._syncer = syncer

    @property
    def _logger(self):
        """
        Shortcut to the syncer logger.
        """
        return self._syncer._logger

    @property
    def bridge(self):
        """
        Return a connected Jira handle.
        """
        return self._syncer.bridge

    @property
    def shotgun(self):
        """
        Return a connected :class:`ShotgunSession` instance.
        """
        return self._syncer.shotgun

    @property
    def jira(self):
        """
        Return a connected Jira handle.
        """
        return self._syncer.jira

    def get_jira_project(self, project_key):
        """
        Retrieve the Jira Project with the given key, if any.

        :returns: A :class:`jira.resources.Project` instance or None.
        """
        for jira_project in self.jira.projects():
            if jira_project.key == project_key:
                return jira_project
        return None

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        Must be re-implemented in deriving classes.

        :returns: `True if the event is accepted for processing, `False` otherwise.
        """
        raise NotImplementedError

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Shotgun event for the given Shotgun Entity

        Must be re-implemented in deriving classes.

        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event meta data for the change.
        """
        raise NotImplementedError

    def accept_jira_event(self, resource_type, resource_id, event):
        """
        Accept or reject the given event for the given Jira resource.

        Must be re-implemented in deriving classes.

        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event is accepted for processing, False otherwise.
        """
        raise NotImplementedError

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
