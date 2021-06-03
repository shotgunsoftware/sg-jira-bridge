# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import logging


class Syncer(object):
    """
    A class handling syncing between ShotGrid and Jira.

    All Syncers should define a list of :class:`~handlers.SyncHandler` which should reject
    or accept and process events.
    """

    def __init__(self, name, bridge, **kwargs):
        """
        Instatiate a new syncer for the given bridge.

        :param str name: A unique name for the syncer.
        :param bridge: A :class:`~sg_jira.Bridge` instance.
        """
        super(Syncer, self).__init__()
        self._name = name
        self._bridge = bridge
        # Set a logger per instance: this allows to filter logs with the
        # syncer name, or even have log file handlers per syncer
        self._logger = logging.getLogger(__name__).getChild(self._name)

    @property
    def bridge(self):
        """
        Returns the :class:`~sg_jira.Bridge` instance used by this syncer.
        """
        return self._bridge

    @property
    def shotgun(self):
        """
        Return a connected :class:`~shotgun_session.ShotgunSession` instance.
        """
        return self._bridge.shotgun

    @property
    def jira(self):
        """
        Return a connected Jira handle.
        """
        return self._bridge.jira

    @property
    def handlers(self):
        """
        Needs to be re-implemented in deriving classes and return a list of
        :class:`~handlers.SyncHandler` instances.
        """
        raise NotImplementedError

    def setup(self):
        """
        Check the Jira and ShotGrid site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """
        self._logger.debug(
            "Checking if the SG and Jira sites are correctly configured."
        )
        for handler in self.handlers:
            handler.setup()

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
        Accept or reject the given event for the given ShotGrid Entity.

        :returns: A :class:`~handlers.SyncHandler` instance if the event is accepted for
                  processing, `None` otherwise.
        """

        # Sanity check the event before checking with handlers
        # We require a non empty event.
        if not event:
            return None

        # Check we have a Project
        if not event.get("project"):
            self._logger.debug("Rejecting event %s with no project." % event)
            return None

        # Check the event meta data
        meta = event.get("meta")
        if not meta:
            self._logger.debug("Rejecting event %s with no meta data." % event)
            return None

        if meta.get("type") != "attribute_change":
            self._logger.debug(
                "Rejecting event %s with wrong or missing event type." % event
            )
            return None

        field = meta.get("attribute_name")
        if not field:
            self._logger.debug(
                "Rejecting event %s with missing attribute name." % (event)
            )
            return None

        # Check we didn't trigger the event to avoid infinite loops.
        user = event.get("user")
        current_user = self._bridge.current_shotgun_user
        if user and current_user:
            if (
                user["type"] == current_user["type"]
                and user["id"] == current_user["id"]
            ):
                self._logger.debug("Rejecting event %s created by us." % event)
                return None

        # Loop over all handlers and return the first one which accepts the
        # event for the given entity.
        # Note: it seems safer to return a single handler than a list of all
        # handlers which could process a given event. Otherwise, one handler
        # could undo what is set by another one without the first one being
        # aware of it. The assumption is that complicated logic can always be
        # implemented in a single handler.
        for handler in self.handlers:
            if handler.accept_shotgun_event(entity_type, entity_id, event):
                self._logger.debug("Dispatching event to %s" % handler)
                return handler

        self._logger.debug(
            "Event %s was rejected by all handlers %s" % (event, self.handlers,)
        )
        return None

    def accept_jira_event(self, resource_type, resource_id, event):
        """
        Accept or reject the given event for the given Jira resource.

        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: A :class:`~handlers.SyncHandler` instance if the event is accepted for
                  processing, `None` otherwise.
        """
        # Check we didn't trigger the event to avoid infinite loops.
        user = event.get("user")
        if user:
            if (
                self.bridge.jira.is_jira_cloud
                and user["accountId"] == self.bridge.jira.myself()["accountId"]
            ):
                self._logger.debug(
                    "Rejecting event %s triggered by us (%s)"
                    % (event, user["accountId"],)
                )
                return None

            # TODO: It's hard to tell if these next to ifs are actually needed anymore.
            # From testing it seems that accountId is always set, so testing for name
            # and emailAddress is probably not needed anymore. We've left these tests
            # for now as we don't have access to a JIRA local instance to test on, which
            # may (but unlikely) behave differently.

            # On GDPR compliant versions of JIRA, the name field is not returned.
            if (
                "name" in user
                and user["name"].lower() == self.bridge.current_jira_username.lower()
            ):
                self._logger.debug(
                    "Rejecting event %s triggered by us (%s)" % (event, user["name"],)
                )
                return None

            # The email field is always present, even on GDPR versions of JIRA, but set to "?".
            # Protect ourselves here by testing for it's presence since it wouldn't be surprising
            # if it was completely removed at some point.
            if (
                "emailAddress" in user
                and user["emailAddress"].lower()
                == self.bridge.current_jira_username.lower()
            ):
                self._logger.debug(
                    "Rejecting event %s triggered by us (%s)"
                    % (event, user["emailAddress"],)
                )
                return None

        # Loop over all handlers and return the first one which accepts the
        # event for the given entity
        # Note: it seems safer to return a single handler than a list of all
        # handlers which could process a given event. Otherwise, one handler
        # could undo what is set by another one without the first one being
        # aware of it. The assumption is that complicated logic can always be
        # implemented in a single handler.
        for handler in self.handlers:
            if handler.accept_jira_event(resource_type, resource_id, event):
                self._logger.debug("Dispatching event to %s" % handler)
                return handler

        self._logger.debug(
            "Event %s was rejected by all handlers %s" % (event, self.handlers,)
        )
        return None
