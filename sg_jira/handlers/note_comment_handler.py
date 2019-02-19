# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

from jira import JIRAError

from ..constants import SHOTGUN_JIRA_ID_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD
from .sync_handler import SyncHandler

# Template used to build Jira comments body from a Note.
COMMENT_BODY_TEMPLATE = """
[Shotgun Note|%s]
{panel:title=%s}
%s
{panel}
"""


class NoteCommentHandler(SyncHandler):
    """
    Sync a Shotgun Task Note with a comment attached to the associated Jira Issue for
    this Task.

    .. note:: The same Shotgun Note can be attached to multiple Tasks, but it is
              not possible to share the same comment across multiple Issues in
              Jira. If a Note is attached to multiple Tasks, only one Issue comment
              will be updated.
    """
    # Define the mapping between Shotgun Note fields and Jira Comment fields.
    # If the Jira target is None, it means the target field is not settable
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
        self._shotgun.assert_field("Note", SHOTGUN_JIRA_ID_FIELD, "text")

    def _supported_shotgun_fields_for_shotgun_event(self):
        """
        Return the list of Shotgun fields that this handler can process for a
        Shotgun to Jira event.
        """
        return self.__NOTE_FIELDS_MAPPING.keys()

    def _get_jira_comment_body(self, shotgun_note):
        """
        Return a body value to update a Jira comment from the given Shotgun Note.

        :param shotgun_note: A Shotgun Note dictionary.
        :returns: A string.
        """
        return COMMENT_BODY_TEMPLATE % (
            self._shotgun.get_entity_page_url(shotgun_note),
            shotgun_note["subject"],
            shotgun_note["content"],
        )

    def _get_jira_issue_comment(self, jira_issue_key, jira_comment_id):
        """
        Retrieve the Jira comment with the given id attached to the given Issue.

        .. note:: Jira comments can't live without being attached to an Issue,
                  so we use a "<Issue key>/<Comment id>" key to reference a
                  particular comment.

        :param str jira_issue_key: A Jira Issue key.
        :param str jira_comment_id: A Jira Comment id.
        :returns: A :class:`jira.resources.Comment` instance or None.
        """
        jira_comment = None
        try:
            jira_comment = self._jira.comment(
                jira_issue_key, jira_comment_id
            )
        except JIRAError as e:
            # Jira raises a 404 error if it can't find the Comment: catch the
            # error and keep the None value
            if e.status_code == 404:
                pass
            else:
                raise
        return jira_comment

    def accept_shotgun_event(self, entity_type, entity_id, event):
        """
        Accept or reject the given event for the given Shotgun Entity.

        :returns: `True if the event is accepted for processing, `False` otherwise.
        """
        # Note: we don't accept events for the SHOTGUN_SYNC_IN_JIRA_FIELD field
        # but we process them. Accepting the event is done by a higher level handler.

        # We only accept Note
        if entity_type != "Note":
            return False
        meta = event["meta"]
        field = meta["attribute_name"]
        if field not in self._supported_shotgun_fields_for_shotgun_event():
            self._logger.debug(
                "Rejecting event %s with unsupported field %s." % (
                    event, field
                )
            )
            return False

        return True

    @property
    def _shotgun_note_fields(self):
        return [
            "created_by",
            "project",
            "project.Project.%s" % SHOTGUN_JIRA_ID_FIELD,
            "project.Project.name",
            "tasks",
            SHOTGUN_JIRA_ID_FIELD,
        ] + self._supported_shotgun_fields_for_shotgun_event()

    def _parse_note_jira_key(self, shotgun_note):
        """
        Parse the Jira key value set in the given Shotgun Note and return the Jira
        Issue key and the Jira comment id it refers to, if it is not empty.

        :returns: A tuple with a Jira Issue key and a Jira comment id, or
                  `None, None`.
        :raises: ValueError if the Jira key is invalid.
        """
        if not shotgun_note[SHOTGUN_JIRA_ID_FIELD]:
            return None, None
        parts = shotgun_note[SHOTGUN_JIRA_ID_FIELD].split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(
                "Invalid Jira comment id %s, it must be "
                "'<jira issue key>/<jira comment id>'" % (
                    shotgun_note[SHOTGUN_JIRA_ID_FIELD]
                )
            )
        return parts[0], parts[1]

    def process_shotgun_event(self, entity_type, entity_id, event):
        """
        Process the given Shotgun event for the given Shotgun Entity

        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event for the change.
        :returns: True if the event was successfully processed, False if the
                  sync didn't happen for any reason.
        """
        meta = event["meta"]
        shotgun_field = meta["attribute_name"]

        # Note: we don't accept events for the SHOTGUN_SYNC_IN_JIRA_FIELD field
        # but we process them.
        # Accepting the event is done by a higher level handler.
        if shotgun_field == SHOTGUN_SYNC_IN_JIRA_FIELD:
            return self._sync_shotgun_task_notes_to_jira(
                {"type": entity_type, "id": entity_id}
            )

        sg_entity = self._shotgun.consolidate_entity(
            {"type": entity_type, "id": entity_id},
            fields=self._shotgun_note_fields
        )
        if not sg_entity:
            self._logger.warning("Unable to retrieve a %s with id %d" % (
                entity_type,
                entity_id
            ))
            return False

        meta = event["meta"]
        shotgun_field = meta["attribute_name"]

        # Update existing synced comment (if any) Issue attachment
        if shotgun_field == "tasks":
            return self._sync_note_tasks_change_to_jira(
                sg_entity,
                meta["added"],
                meta["removed"],
            )

        # Update the Jira comment body
        return self._sync_note_content_to_jira(sg_entity)

    def _sync_note_content_to_jira(self, shotgun_note):
        """
        Update an existing Jira Comment body from the Shotgun Note fields.

        :param shotgun_note: A Shotgun Note dictionary.
        :returns: `True` if a Jira Comment was updated, `False` otherwise.
        """
        jira_issue_key, jira_comment_id = self._parse_note_jira_key(shotgun_note)
        if jira_issue_key and jira_comment_id:
            # Double check that there is a valid Task linked to this Note and the
            # Jira Issue. We have to do this to check for the Task "Sync in Jira"
            # checkbox value.
            task_ids = [x["id"] for x in shotgun_note["tasks"]]
            if not task_ids or not self._shotgun.find_one(
                "Task", [
                    ["id", "in", task_ids],
                    [SHOTGUN_JIRA_ID_FIELD, "is", jira_issue_key],
                    [SHOTGUN_SYNC_IN_JIRA_FIELD, "is", True]
                ],
            ):
                self._logger.debug(
                    "Not updating Jira Issue %s comment %s from Shotgun Note %s" % (
                        jira_issue_key,
                        jira_comment_id,
                        shotgun_note
                    )
                )
                return False

            jira_comment = self._get_jira_issue_comment(
                jira_issue_key,
                jira_comment_id
            )
            if jira_comment:
                self._logger.debug(
                    "Updating comment %s attached to Jira Issue %s" % (
                        jira_comment, jira_issue_key
                    )
                )
                jira_comment.update(
                    body=self._get_jira_comment_body(shotgun_note)
                )
                return True

        return False

    def _sync_note_tasks_change_to_jira(self, shotgun_note, added, removed):
        """
        Update Jira with tasks changes for the given Shotgun Note.

        :param shotgun_note: A Shotgun Note dictionary.
        :param added: A list of Shotgun Task dictionaries which were added to
                      the given Note.
        :param removed: A list of Shotgun Task dictionaries which were removed from
                        the given Note.
        :returns: `True` if the given changes could be processed sucessfully,
                  `False` otherwise.
        """

        jira_issue_key, jira_comment_id = self._parse_note_jira_key(shotgun_note)

        updates = 0
        if jira_issue_key and removed:
            # Check if we should delete the comment because it was attached to
            # a synced Task which has been removed.
            # Retrieve a task with the given Issue key
            sg_tasks = self._shotgun.find(
                "Task", [
                    ["id", "in", [x["id"] for x in removed]],
                    [SHOTGUN_JIRA_ID_FIELD, "is", jira_issue_key],
                    [SHOTGUN_SYNC_IN_JIRA_FIELD, "is", True]
                ],
                ["content"]
            )
            if sg_tasks:
                if len(sg_tasks) > 1:
                    # Issue a warning about a potential problem
                    self._logger.warning(
                        "Multiple Shotgun Tasks seem to linked to the same "
                        "Jira Issue: %s." % sg_tasks
                    )
                jira_comment = self._get_jira_issue_comment(
                    jira_issue_key,
                    jira_comment_id
                )
                if jira_comment:
                    self._logger.debug(
                        "Deleting comment %s attached to Jira Issue %s" % (
                            jira_comment, jira_issue_key
                        )
                    )
                    jira_comment.delete()
                    updates += 1
                # Unset the values so a new comment can be attached to another
                # issue when processing the added Tasks.
                jira_issue_key = None
                jira_comment_id = None

        if not jira_issue_key and added:
            # Collect the list of Tasks which are linked to Jira Issues
            sg_tasks = self._shotgun.find(
                "Task", [
                    ["id", "in", [x["id"] for x in added]],
                    [SHOTGUN_JIRA_ID_FIELD, "is_not", None],
                    [SHOTGUN_SYNC_IN_JIRA_FIELD, "is", True]
                ],
                ["content", SHOTGUN_JIRA_ID_FIELD, SHOTGUN_SYNC_IN_JIRA_FIELD]
            )
            if len(sg_tasks) > 1:
                self._logger.warning(
                    "Found multiple Tasks %s linked to a Jira Issue for Note %s, "
                    "only one will be updated" % (
                        sg_tasks, shotgun_note,
                    )
                )
            for sg_task in sg_tasks:
                # Retrieve the Jira Issue to ensure the Jira key value is valid
                jira_issue = self.get_jira_issue(sg_task[SHOTGUN_JIRA_ID_FIELD])
                if not jira_issue:
                    self._logger.warning(
                        "Unable to retrieve the Jira Issue %s for Note %s" % (
                            sg_task[SHOTGUN_JIRA_ID_FIELD],
                            shotgun_note,
                        )
                    )
                    continue
                # Add the Note as a comment to the Issue
                self._logger.debug(
                    "Adding Note %s as a Jira comment for %s" % (
                        shotgun_note,
                        jira_issue,
                    )
                )
                jira_comment = self._jira.add_comment(
                    jira_issue,
                    self._get_jira_comment_body(shotgun_note),
                    visibility=None,  # TODO: check if Note properties should drive this
                    is_internal=False
                )
                jira_issue_key = jira_issue.key
                jira_comment_id = jira_comment.id
                updates += 1
                break

        # Update the Jira comment key in Shotgun
        comment_key = None
        if jira_issue_key and jira_comment_id:
            comment_key = "%s/%s" % (jira_issue_key, jira_comment_id)
        if comment_key != shotgun_note[SHOTGUN_JIRA_ID_FIELD]:
            self._logger.debug(
                "Updating %s with Jira comment key %s" % (
                    shotgun_note,
                    comment_key,
                )
            )
            self._shotgun.update(
                shotgun_note["type"],
                shotgun_note["id"],
                {SHOTGUN_JIRA_ID_FIELD: comment_key}
            )
            updates += 1

        return bool(updates)

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

    def _sync_shotgun_task_notes_to_jira(self, shotgun_task):
        """
        Sync all Notes attached to the given Shotgun Task to Jira.

        :param shotgun_taks: A Shotgun Task dictionary.
        :returns: `True` if any update happened, `False` otherwise.
        """
        shotgun_notes = self._shotgun.find(
            "Note",
            [["tasks", "is", shotgun_task]],
            self._shotgun_note_fields
        )
        self._logger.debug(
            "Retrieved Notes %s linked to Task %s" % (shotgun_notes, shotgun_task)
        )
        updates = 0
        for shotgun_note in shotgun_notes:
            res = self._sync_note_tasks_change_to_jira(
                shotgun_note,
                added=[shotgun_task],
                removed=[]
            )
            if res:
                updates += 1
            if self._sync_note_content_to_jira(shotgun_note):
                updates += 1

        return bool(updates)
