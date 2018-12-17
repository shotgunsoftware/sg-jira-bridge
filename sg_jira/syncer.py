# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import logging
from jira import JIRAError


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

    @property
    def bridge(self):
        """
        Returns the :class:`sg_jira.Bridge` instance used by this syncer.
        """
        return self._bridge

    @property
    def shotgun(self):
        """
        Return a connected Shotgun handle.
        """
        return self._bridge.shotgun

    @property
    def jira(self):
        """
        Return a connected Jira handle.
        """
        return self._bridge.jira

    def setup(self):
        """
        Check the Jira and Shotgun site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """
        pass

    def get_jira_project(self, project_key):
        """
        Retrieve the Jira Project with the given key, if any.

        :returns: A :class:`jira.resource.Project` instance or None.
        """
        for jira_project in self._bridge.jira.projects():
            if jira_project.key == project_key:
                return jira_project
        return None

    def get_jira_issue(self, issue_key):
        """
        Retrieve the Jira Issue with the given key, if any.

        :param str issue_key: A Jira Issue key to look for.
        :returns: A :class:`jira.resource.Issue` instance or None.
        :raises: UserWarning if the Issue if not bound to any Project.
        """
        jira_issue = None
        try:
            jira_issue = self.jira.issue(issue_key)
            if not jira_issue.fields.project:
                raise UserWarning(
                    "Jira Issue %s is not bound to any Project." % issue_key
                )
        except JIRAError as e:
            if e.status_code == 404:
                pass
            else:
                raise

    def create_jira_issue_for_entity(
        self,
        sg_entity,
        jira_project,
        issue_type,
        summary,
        description=None,
        **properties
    ):
        """
        Create a Jira issue linked to the given Shothgun Entity with the given properties

        :param sg_entity: A Shotgun Entity dictionary.
        :param jira_project: A :class:`jira.resource.Project` instance.
        :param str issue_type: The target Issue type name.
        :param str summary: The Issue summary.
        :param str description: An optional description for the Issue.
        :param properties: Arbitrary properties to set on the Jira Issue.
        """
        jira_issue_type = self.jira.issue_type_by_name(issue_type)
        # Retrieve creation meta data for the project / issue type
        create_meta_data = self.jira.createmeta(
            jira_project,
            issuetypeIds=jira_issue_type.id,
            expand="projects.issuetypes.fields"
        )
        # We asked for a single project / single issue type, so we can just pick
        # the first entry, if it exists
        if not create_meta_data["projects"] or not create_meta_data["projects"][0]["issuetypes"]:
            raise RuntimeError(
                "Unable to retrieve create meta data for Project %s Issue type %s."  % (
                    str(jira_project),
                    str(jira_issue_type),
                )
            )
        fields_createmeta = create_meta_data["projects"][0]["issuetypes"][0]["fields"]

        # Note that JIRA raises an error if there are new line characters in the
        # summary for an Issue or if the description field is empty.
        if not description:
            description = "%s (%d)" % (sg_entity["type"], sg_entity["id"])
        data = {
            "project": jira_project.raw,
            "summary": summary.replace("\n", "").replace("\r", ""),
            "description": description,
            self.bridge.jira_shotgun_id_field: "%s" % sg_entity["id"],
            self.bridge.jira_shotgun_type_field: sg_entity["type"],
            "issuetype": jira_issue_type.raw,
            "reporter": {"name": self.jira.current_user()},
        }
        # Check if we are missing any required data which does not have a default
        # value.
        missing = []
        for k, jira_create_field in fields_createmeta.iteritems():
            if k not in data:
                if jira_create_field["required"] and not jira_create_field["hasDefaultValue"]:
                    missing.append(jira_create_field["name"])
        if missing:
            raise ValueError(
                "The following data is missing in order to create a Jira %s Issue: %s" % (
                    data["issuetype"]["name"],
                    missing,
                )
            )
        self.jira.create_issue(fields=data)

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :returns: True if the event is accepted for processing, False otherwise.
        """

        # We require a non empty event.
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

        Must be re-implemented in deriving classes.

        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event meta data for the change.
        """
        raise NotImplementedError

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

