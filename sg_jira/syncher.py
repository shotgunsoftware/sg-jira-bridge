# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import logging


class Syncher(object):
    """
    A class handling synching between Shotgun and Jira
    """

    def __init__(self, name, shotgun, jira, **kwargs):
        super(Syncher, self).__init__()
        self._name = name
        self._shotgun = shotgun
        self._jira = jira
        # Set a logger per instance: this allows to filter logs with the
        # syncher name, or even have log file handlers per syncher
        self._logger = logging.getLogger(__name__).getChild(self._name)

    def setup(self):
        """
        TBD: could be used to check sites, create custom fields, etc...
        """
        pass

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        TBD: could be used to implement special logic to ignore some events
        """
        return True

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Shotgun event for the given Shotgun Entity

        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entityto sync.
        :param event: A dictionary with the event meta data for the change.
        """
        self._logger.info("synching in Jira %s(%d) for event %s" % (
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
        self._logger.info("synching in SG %s(%s) for event %s" % (
            resource_type,
            resource_id,
            event
        ))

