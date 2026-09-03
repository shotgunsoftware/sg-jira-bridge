# SG-38522 — Support Syncing Note Threaded Conversations

## Background

In Flow Production Tracking (FPTR), a `Note` entity can have threaded replies
via the `Reply` entity type. These form a conversation thread under the parent
Note. Jira Cloud now supports native comment threading, making it possible to
map FPTR reply threads directly to Jira comment replies.

This feature is scoped to the **`EntitiesGenericSyncer`** only.
`NoteCommentHandler` / `TaskIssueSyncer` are out of scope.

## Current Behaviour

- `EntitiesGenericHandler` syncs FPTR `Note` entities to Jira Issue comments.
- The Jira comment ID is stored on the Note as `<issue_key>/<comment_id>` in
  `SHOTGUN_JIRA_ID_FIELD`.
- There is no custom field on the Jira comment side — tracking is entirely via
  `SHOTGUN_JIRA_ID_FIELD` on the FPTR entity.
- `Note` is in `__ENTITIES_NOT_FLAGGED_AS_SYNCED` — it syncs automatically when
  its linked Task is synced, without a "Sync in Jira" checkbox.
- **FPTR `Reply` entities are entirely unhandled.** They are never synced.

## Proposed Approach — Jira Cloud Native Comment Replies

Map each FPTR `Reply` to a Jira comment reply on the parent Note's Jira comment,
using the Jira Cloud REST API v3 comment threading endpoints.

### Data Model

```
FPTR Note    →  Jira Issue Comment         (existing)
FPTR Reply   →  Jira Comment Reply         (new)
```

A FPTR `Reply` has:
- `content` — reply body text
- `user` / `created_by` — author
- `entity` — parent `Note` (single-entity link)

#### ID Tracking

FPTR `Reply` entities do not support custom fields, so `SHOTGUN_JIRA_ID_FIELD`
cannot be stored directly on a Reply. Instead, a new custom text field
(`SHOTGUN_JIRA_REPLY_IDS_FIELD`, e.g. `sg_jira_reply_ids`) is added to the
**parent `Note`** entity. It stores a JSON mapping of FPTR Reply IDs to Jira
reply IDs:

```json
{"12345": "jira-reply-id-abc", "67890": "jira-reply-id-xyz"}
```

This field must be created on the FPTR site by the user, the same way
`SHOTGUN_JIRA_ID_FIELD` is created. The bridge will assert its existence on
startup (via `setup()`).

### Sync Directions

**FPTR → Jira:**
1. A `Reply` is created/updated/deleted on a FPTR `Note`.
2. The bridge receives a FPTR event for entity type `Reply`.
3. The handler fetches the parent `Note` via `Reply.entity`.
4. If the Note's `SHOTGUN_JIRA_ID_FIELD` is empty (Note not yet synced to Jira),
   the event is skipped silently.
5. It reads `<issue_key>/<comment_id>` from the Note's `SHOTGUN_JIRA_ID_FIELD`.
6. It creates/updates/deletes the Jira comment reply, using the
   `sg_jira_reply_ids` mapping on the Note to resolve the Jira reply ID.
7. It updates `sg_jira_reply_ids` on the Note to reflect the change.

**Jira → FPTR:**

Bidirectional sync is possible via a two-step lookup using the Note's mapping
field:
1. A Jira reply event arrives (event type TBD — see Open Questions).
2. The bridge extracts `<issue_key>/<comment_id>` and the Jira reply ID.
3. It finds the FPTR Note by querying on `<issue_key>/<comment_id>` via
   `SHOTGUN_JIRA_ID_FIELD` (existing mechanism).
4. It reads `sg_jira_reply_ids` on that Note and reverse-looks up the FPTR
   Reply ID from the Jira reply ID.
5. It creates/updates/deletes the FPTR Reply accordingly.

### Jira API

Jira Cloud REST API v3 exposes comment reply endpoints:
- `POST /rest/api/3/issue/{issueKey}/comment/{commentId}/replies` — create reply
- `GET /rest/api/3/issue/{issueKey}/comment/{commentId}/replies` — list replies
- `PUT /rest/api/3/issue/{issueKey}/comment/{commentId}/replies/{replyId}` — update
- `DELETE /rest/api/3/issue/{issueKey}/comment/{commentId}/replies/{replyId}` — delete

> **Note:** The `jira` Python library likely does not yet expose these endpoints
> natively. Direct REST calls via `self._jira._session` (or a new
> `JiraSession` helper method) will be needed.

### Stale Mapping Entries

If a Jira reply is deleted directly in Jira (not via FPTR), the corresponding
entry in `sg_jira_reply_ids` becomes stale. The bridge will handle this with a
404 check when fetching a Jira reply: if not found, clean the stale entry from
the mapping and log a warning.

## Implementation Areas

### `sg_jira/constants.py`

- Add `SHOTGUN_JIRA_REPLY_IDS_FIELD` constant for the new Note mapping field.

### `sg_jira/handlers/entities_generic_handler.py`

- Add `"Reply"` to `__ENTITIES_NOT_FLAGGED_AS_SYNCED`.
- Add `__REPLY_SG_FIELDS = ["content", "user", "entity"]`.
- Extend `_supported_shotgun_entities_for_shotgun_event()` to include `Reply`
  when configured.
- Add `_supported_shotgun_fields_for_shotgun_event()` handling for `"Reply"`.
- Add `_create_jira_reply(sg_reply)` — POST to Jira reply endpoint, update
  `sg_jira_reply_ids` on the parent Note.
- Add `_update_jira_reply(sg_reply)` — resolve Jira reply ID from parent Note's
  mapping, PUT to Jira reply endpoint.
- Add `_delete_jira_reply(sg_reply)` — resolve Jira reply ID from parent Note's
  mapping, DELETE from Jira, remove entry from mapping.
- Add `__get_jira_reply_id_from_note(sg_note, sg_reply_id)` to read and parse
  the `sg_jira_reply_ids` mapping.
- Extend `process_shotgun_event()` to route `Reply` entity events.
- In `accept_jira_event` and `process_jira_event`, check for `parentId` on the
  comment payload to distinguish replies from top-level comments. If `parentId`
  is present, route to Reply handling; otherwise use existing Note handling.
- For Jira → FPTR replies: look up the parent Note via
  `<issue_key>/<parentId>` in `SHOTGUN_JIRA_ID_FIELD`, then reverse-lookup the
  FPTR Reply ID from `sg_jira_reply_ids` on that Note.
- No new webhook event types are needed — `comment_created`, `comment_updated`,
  and `comment_deleted` cover replies via the `parentId` field.

### `sg_jira/jira_session.py` (or equivalent)

- Add helper methods for the Jira reply REST endpoints, wrapping direct REST
  calls since `jira-python` doesn't expose them natively.

### `settings.py`

- Add `enable_reply_syncing: True` to the `Note` entry in the `entity_mapping`
  list under the `entities` syncer. Reply has no settings of its own - it fully
  inherits `sync_direction`/`sync_deletion_direction` from that Note entry, e.g.:
  ```python
  {
      "sg_entity": "Note",
      "sync_deletion_direction": "both_way",
      "enable_reply_syncing": True,
  }
  ```

### `tests/`

- Unit tests for reply create/update/delete (FPTR → Jira).
- Unit tests for the `sg_jira_reply_ids` mapping read/write/cleanup.
- Unit tests for the two-step Jira → FPTR lookup via the Note mapping.
- Stale entry (404) handling test.

## Jira Reply Webhook Behaviour (Confirmed)

Jira Cloud does **not** fire a distinct event type for comment replies. Replies
arrive as standard `comment_created` / `comment_updated` / `comment_deleted`
events — the same as top-level comments.

Replies are distinguished by the presence of a **`parentId`** field on the
comment object in the payload, containing the ID of the parent comment:

```json
{
  "webhookEvent": "comment_created",
  "comment": {
    "id": "10157",
    "parentId": 10155,
    "body": "[~accountid:...] another reply",
    ...
  }
}
```

Top-level comments have no `parentId` field. This is the sole distinguishing
signal the bridge can use to route events correctly.

**Current behaviour (bug):** The bridge currently treats replies as regular
`comment_created` events and would create a new FPTR `Note` for comment `10157`
rather than a `Reply` linked to the Note for comment `10155`. The `parentId`
check does not yet exist.

## Acceptance Criteria

- [ ] When a `Reply` is created on a synced FPTR Note, a Jira comment reply
  appears on the corresponding Jira Issue comment.
- [ ] When a `Reply` body is edited in FPTR, the Jira reply is updated.
- [ ] When a `Reply` is deleted in FPTR, the Jira reply is deleted (subject to
  `sync_deletion_direction` setting).
- [ ] The `sg_jira_reply_ids` mapping on the parent Note is kept in sync with
  all create/update/delete operations.
- [ ] A stale mapping entry (Jira reply deleted outside the bridge) is cleaned
  up gracefully with a warning log.
- [ ] Existing Note sync behaviour is fully unchanged (no regression).
- [ ] All new paths have unit test coverage.
- [ ] Jira → FPTR reply sync is implemented once webhook event behaviour is
  confirmed (open question 1).

## Files Likely to Change

| File | Change |
|------|--------|
| `sg_jira/constants.py` | Add `SHOTGUN_JIRA_REPLY_IDS_FIELD` |
| `sg_jira/handlers/entities_generic_handler.py` | Core logic for Reply entity handling |
| `sg_jira/jira_session.py` | Helper methods for Jira reply REST endpoints |
| `settings.py` | Add enable_reply_syncing to the Note entity_mapping entry |
| `tests/` | New tests for reply sync |
