# SG-38522 — Rewrite Jira User Mentions for Flow PT Readability

## Background

Jira comment/reply bodies use wiki-markup mention syntax when a user is
@-tagged, e.g. `[~accountid:557058:276f63c9-3d4b-4562-a4a2-3abfacc11442]`.
Synced verbatim into Flow Production Tracking (FPTR) — which has no user
tagging syntax — this reads as raw, unreadable junk, e.g.:

```
[~accountid:557058:276f63c9-3d4b-4562-a4a2-3abfacc11442] reply from Jira 1 Edit from Flow 1
```

This bridge already uses Jira REST API v2 by default (confirmed:
`jira.client.JIRA.DEFAULT_OPTIONS["rest_api_version"] == "2"`), so comment
bodies are always returned as plain wiki-markup text, never Atlassian
Document Format (ADF) JSON. This significantly simplifies the design — no ADF
parsing is required, only string/regex handling.

## Goal

When a Jira mention's `accountId` matches an FPTR user (via the existing
`sg_jira_account_id` field, see `hook.get_sg_user_from_jira_user`), rewrite it
to a readable FPTR-side placeholder. Reverse the transform when that content
syncs back to Jira. If no matching user is found in either direction, leave
the original text untouched.

## Placeholder Format

```
[mention:<sg_user_id>:<sg_name_no_spaces>]
```

Example: `[mention:88:PhilipScadding]`

- `<sg_user_id>` is the FPTR `HumanUser` id — the **source of truth** for the
  reverse (FPTR → Jira) lookup.
- `<sg_name_no_spaces>` is the user's FPTR `name` field with whitespace
  stripped — purely cosmetic, for human readability. It is **never** used for
  matching, so a stale name (e.g. after the user is renamed in FPTR) does not
  break the reverse lookup.

## Scope

Applies to **both** top-level Note comments and Reply comments — any Jira
comment body handled by `EntitiesGenericHandler` can contain a mention, not
just replies.

## Design

Two pure string → string conversion functions, added to `sg_jira/hook.py`
(the existing customization point for this kind of value-mapping logic,
alongside `compose_jira_comment_body` and `get_sg_user_from_jira_user`):

### `jira_body_to_sg(self, body)`

- Regex-scans `body` for all occurrences of `\[~accountid:([^\]]+)\]`.
- For each match, looks up an FPTR `HumanUser` via
  `sg_filters = [["sg_jira_account_id", "is", accountid]]` (reusing the same
  filter `get_sg_user_from_jira_user` already uses for Jira Cloud).
- If found, replaces the match with `[mention:<id>:<name_no_spaces>]`.
- If not found, leaves that particular mention unchanged.
- Returns the rewritten body.

### `sg_body_to_jira(self, body)`

- Regex-scans `body` for all occurrences of `\[mention:(\d+):([^\]]*)\]`.
- For each match, looks up the FPTR `HumanUser` by id (`sg.find_one`).
- If found and `sg_jira_account_id` is set, replaces the match with
  `[~accountid:<that_id>]`.
- If the user isn't found, or has no `sg_jira_account_id`, leaves that
  particular placeholder unchanged.
- Returns the rewritten body.

Both functions handle multiple mentions in a single body (global replace) and
have no side effects beyond FPTR read lookups — straightforward to unit test
against a mocked Shotgun connection.

## Call Sites

Applied in `sg_jira/handlers/entities_generic_handler.py`, at the point body
text crosses the FPTR/Jira boundary:

| Direction | Method | Applied to |
|---|---|---|
| FPTR → Jira (Note) | `_create_jira_comment` | composed comment body before `self._jira.add_comment(...)` |
| FPTR → Jira (Reply) | `_process_reply_shotgun_event` | `reply_body` before `self._jira.add_comment_reply(...)` |
| Jira → FPTR (Note) | `_sync_jira_comment_to_sg` | comment body before writing to the Note |
| Jira → FPTR (Reply) | `_sync_jira_reply_to_sg` | `comment_event["body"]` before writing to the Reply |

## Out of Scope / Non-Goals

- No attempt to support ADF-formatted bodies (Jira REST API v3) — this bridge
  doesn't use v3.
- No validation/repair of a placeholder whose embedded name no longer matches
  the FPTR user's current name — the id is authoritative and the name is
  cosmetic only.
- No handling of a user manually typing text that happens to match either
  placeholder pattern — this is treated as an acceptable edge case, not
  addressed.

## Acceptance Criteria

- [ ] A Jira mention referencing an FPTR-linked user renders as
      `[mention:<id>:<name>]` in the synced FPTR Note/Reply.
- [ ] A Jira mention referencing a Jira user with no FPTR mapping is left as
      `[~accountid:...]`, unchanged.
- [ ] An FPTR `[mention:<id>:<name>]` placeholder referencing a Jira-linked
      user renders as `[~accountid:...]` in the synced Jira comment/reply.
- [ ] An FPTR `[mention:<id>:<name>]` placeholder referencing a user with no
      Jira mapping is left unchanged.
- [ ] Bodies with multiple mentions (mixed mapped/unmapped) are handled
      correctly.
- [ ] Unit tests cover both conversion functions in isolation, plus each of
      the 4 call sites.

## Files Likely to Change

| File | Change |
|------|--------|
| `sg_jira/hook.py` | Add `jira_body_to_sg` and `sg_body_to_jira` |
| `sg_jira/handlers/entities_generic_handler.py` | Call the new hook methods at the 4 body-crossing points |
| `tests/` | New tests for both conversion functions and call sites |

## Note on a Related Existing Spec Inaccuracy

`specs/SG-38522-note-thread-sync.md` states Jira Cloud REST API v3 exposes
dedicated reply endpoints (`POST/PUT/DELETE
/rest/api/3/issue/{issueKey}/comment/{commentId}/replies`). This was tested
live against the actual Jira Cloud site during this work and **does not
exist** (`404 No endpoint`). Replies are created via the standard
`POST /rest/api/{2,3}/issue/{issueKey}/comment` endpoint with an added
`parentId` field in the payload — already implemented as
`JiraSession.add_comment_reply`. That spec should be corrected separately;
not addressed here to stay focused on the mention-rewrite feature.
