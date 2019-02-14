# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from jira import JIRAError


class SyncHandler(object):
    """
    Base class to handle a particular sync between Shotgun and Jira.

    Handlers typically handle syncing values between a Shotgun Entity type and
    a Jira resource and are owned by a `:class:`Syncer` instance.

    This base class defines the interface all handlers should support and
    provides some helpers which can be useful to all handlers.
    """

    def __init__(self, syncer):
        """
        Instantiate a handler for the given syncer.

        :param syncer: A :class:`Syncer` instance.
        """
        self._syncer = syncer

    @property
    def _logger(self):
        """
        Return the syncer logger.
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
        return self._syncer.get_jira_project(project_key)

    def get_jira_issue(self, issue_key):
        """
        Retrieve the Jira Issue with the given key, if any.

        :param str issue_key: A Jira Issue key to look for.
        :returns: A :class:`jira.resources.Issue` instance or None.
        :raises: RuntimeError if the Issue if not bound to any Project.
        """
        jira_issue = None
        try:
            jira_issue = self.jira.issue(issue_key)
            if not jira_issue.fields.project:
                # This should never happen as it does not seem possible to
                # have Issues not linked to a project. Report the error if it
                # does happen.
                raise RuntimeError(
                    "Jira Issue %s is not bound to any Project." % issue_key
                )
        except JIRAError as e:
            # Jira raises a 404 error if it can't find the Issue: catch the
            # error and let the method return None in that case.
            if e.status_code == 404:
                pass
            else:
                raise
        return jira_issue

    def setup(self):
        """
        This method can be re-implemented in deriving classes to Check the Jira
        and Shotgun site, ensure that the sync can safely happen and cache any
        value which is slow to retrieve.

        This base implementation does nothing.
        """
        pass

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
