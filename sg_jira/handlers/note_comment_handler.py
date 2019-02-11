# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import jira
from jira import JIRAError

from ..constants import SHOTGUN_JIRA_ID_FIELD
from ..errors import InvalidShotgunValue
from .sync_handler import SyncHandler

BODY_TEMPLATE = """
[Shotgun Note|%s]
{panel:title=%s}
%s
{panel}
"""



class NoteCommentHandler(SyncHandler):

    # Define the mapping between Shotgun Note fields and Jira Comment fields
    # if the Jira target is None, it means the target field is not settable
    # directly.
    __NOTE_FIELDS_MAPPING = {
        "subject": None,
        "content": None,
        "user": None,
        "tasks": None,
    }

    def setup(self):
        """
        Check the Jira and Shotgun site, ensure that the sync can safely happen
        and cache any value which is slow to retrieve.
        """
        self.shotgun.assert_field("Note", SHOTGUN_JIRA_ID_FIELD, "text")

    def supported_shotgun_fields_for_shotgun_event(self):
        """
        Return the list of Shotgun fields that this handler can process for a
        Shotgun to Jira event.
        """
        return self.__NOTE_FIELDS_MAPPING.keys()

    def shotgun_note_url(self, shotgun_note_id):
        return "%s/detail/Note/%d" % (
            self.shotgun.base_url,
            shotgun_note_id,
        )

    def get_jira_comment_body(self, shotgun_note):
        return BODY_TEMPLATE % (
            self.shotgun_note_url(shotgun_note["id"]),
            shotgun_note["subject"],
            shotgun_note["content"],
        )

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :returns: `True if the event is accepted for processing, `False` otherwise.
        """
        # We only accept Note
        if entity_type != "Note":
            return False
        meta = event["meta"]
        field = meta["attribute_name"]
        if field not in self.supported_shotgun_fields_for_shotgun_event():
            self._logger.debug(
                "Rejecting event %s with unsupported or missing field %s." % (
                    event, field
                )
            )
            return False

        return True

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Shotgun event for the given Shotgun Entity

        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event was successfully processed, False if the
                  sync didn't happen for any reason.
        """
        note_fields = [
            "created_by",
            "project",
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
            SHOTGUN_JIRA_ID_FIELD
        ] + self.__NOTE_FIELDS_MAPPING.keys()

        sg_entity = self.shotgun.consolidate_entity(
            {"type": entity_type, "id": entity_id},
            fields=note_fields
        )
        if not sg_entity:
            self._logger.warning("Unable to retrieve a %s with id %d" % (
                entity_type,
                entity_id
            ))
            return False

        if not sg_entity["tasks"]:
            return False

        # Retrieve the Tasks this Note is attached to
        sg_tasks = self.shotgun.find(
            "Task", [
                ["id", "in", [x["id"] for x in sg_entity["tasks"]]],
                [SHOTGUN_JIRA_ID_FIELD, "is_not", None],
            ],
            ["content", SHOTGUN_JIRA_ID_FIELD, ]
        )
        self._logger.debug(
            "Treating Note %s linked to Tasks %s" % (
                sg_entity, sg_tasks,
            )
        )
        jira_comment = None
        jira_issues = []
        for sg_task in sg_tasks:
            if not sg_task[SHOTGUN_JIRA_ID_FIELD]:
                continue
            # Retrieve the Jira Issue for the Task
            jira_issue = self.get_jira_issue(sg_task[SHOTGUN_JIRA_ID_FIELD])
            if not jira_issue:
                self._logger.warning(
                    "Unable to retrieve the Jira Issue %s for Note %s" % (
                        sg_task[SHOTGUN_JIRA_ID_FIELD],
                        sg_entity,
                    )
                )
                continue

            if not sg_entity[SHOTGUN_JIRA_ID_FIELD]:
                # A Jira comment does not yet exists for this Note
                jira_comment = self.jira.add_comment(
                    jira_issue,
                    self.get_jira_comment_body(sg_entity),
                    visibility=None,
                    is_internal=False
                )
                sg_entity[SHOTGUN_JIRA_ID_FIELD] = jira_comment.id
                self.shotgun.update(
                    sg_entity["type"],
                    sg_entity["id"],
                    {SHOTGUN_JIRA_ID_FIELD: jira_comment.id}
                )
            else:
                jira_comment=None
                try:
                    jira_comment = self.jira.comment(
                        jira_issue, sg_entity[SHOTGUN_JIRA_ID_FIELD]
                    )
                except JIRAError as e:
                    # Jira raises a 404 error if it can't find the Comment: catch the
                    # error and keep the None value
                    if e.status_code == 404:
                        pass
                    else:
                        raise
                if jira_comment:
                    self._logger.debug(
                        "Updating comment %s for Jira Issue %s" % (
                            jira_comment,
                            jira_issue,
                        )
                    )
                    jira_comment.update(
                        body=self.get_jira_comment_body(sg_entity)
                    )
            # Note: it is not possible to retrieve a comment without a Jira Issue
            #
            # Explore the Issue comments
            comments = self.jira.comments(jira_issue)
            self._logger.debug("%s" % comments)
            for comment in comments:
                self._logger.debug("%s" % comment)

    def accept_jira_event(self, resource_type, resource_id, event):
        """
        Accept or reject the given event for the given Jira resource.

        Not yet implemented...

        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the event is accepted for processing, False otherwise.
        """
        return False
