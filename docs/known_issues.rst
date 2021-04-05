.. _known_issues:

Known Issues & Compatibility Notes
##################################

Because SG and Jira are both highly customizable and have different APIs,
there are some cases where things may not match up as expected. There are also
cases where certain features have not been implemented yet.

- Deletion events are not handled yet.

- SG Jira Bridge does not create entities in Shotgun, it will only update
  existing ones. This means syncing can only *initiate* from SG and not
  from Jira. If an entity in SG that was synced with an issue in Jira is
  deleted, it will not currently be re-created in Shotgun.

- In most cases only one :class:`~sg_jira.handlers.SyncHandler` can handle a
  given event. The exception is with the **Sync In Jira** event which is a
  special case that is handled by the
  :class:`~sg_jira.handlers.EnableSyncingHandler` which is a container
  for multiple handlers.

- Notes in SG can be linked to multiple entities, but Comments in Jira
  can only be linked to a single Issue. Notes linked to multiple entities in
  SG will be synced in Jira but only linked to a single Issue. There is
  no logic to choosing which Issue the Note is linked to other than the first
  one that the Bridge encounters.

- SG Notes contain a subject and content, while Jira Comments have only
  a body. When syncing Notes from SG to Jira, a special formatting is
  used to mimic the structure that SG uses. Updates to a Comment in Jira
  must retain this formatting otherwise the Comment will not sync back to
  Shotgun.

- Note Replies in SG are not currently handled by SG Jira Bridge. Jira
  has no concept of replies, or threading in Comments. This workflow is
  being investigated.

- Duplicating an Entity in SG that is currently synced with Jira, will
  also duplicate the **Jira Key** field, possibly causing data corruption.
  We recommend not duplicating synced Entities in Shotgun. Alternatively, you
  may enable unique values on the **Jira Key** in Shotgun, however this will
  now generate an error in SG if a synced Entity is duplicated. Perhaps
  it's better than possibly corrupting the synced Jira Issue.

- Jira single-line `Text Field` fields are limited to 255 characters. When
  syncing from SG to Jira, if the SG field is mapped to a Jira
  single-line Text Field, and the value is longer than 255 characters, a
  warning is logged, the synced value will be truncated and an addendum added
  that says to look in SG for the full value. This could cause data loss
  if the field is then updated in Jira which will overwrite the original value
  in Shotgun.
