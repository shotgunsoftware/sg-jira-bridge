.. _jira_project_automation:

Jira Project Automation
#######################

Jira **Project Automation** rules let project admins (not just site admins) drive
the bridge. The bridge supports two ways of doing this, summarised here and
detailed below:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Approach
     - When to use
   * - | **1. Bridge-side normalization**
       | (this page, top section)
     - You want a minimal automation rule and let the bridge fetch the issue
       and build the event for you.
   * - | **2. Webhook-shaped custom JSON**
       | (this page, bottom section)
     - You don't want to change the bridge at all and are happy to hand-craft
       the JSON body using smart values so it mimics a Jira webhook.

Both approaches only work with the
:class:`~sg_jira.handlers.entities_generic_handler.EntitiesGenericHandler` (i.e.
:class:`~sg_jira.entities_generic_syncer.EntitiesGenericSyncer`). The legacy
``EntityIssueHandler`` rejects automation events because they have no changelog.

.. _jira_automation_sync_scope:

Full sync vs. field-change sync
===============================

The two approaches differ in *which* fields the bridge syncs:

* **Approach 1 (bridge-side normalization)** produces events with no Jira
  changelog. The normalizer tags them with an internal
  ``_bridge_automation_full_sync`` flag
  (:data:`~sg_jira.constants.JIRA_EVENT_AUTOMATION_FULL_SYNC`), and the handler
  responds with a **full sync** — every mapped Issue field is pushed to Flow
  Production Tracking, and the sync cascades to the Issue's associated comments
  (Notes) and worklogs (TimeLogs). Use this when you want the rule to reconcile
  the whole Issue rather than a single change.
* **Approach 2 (webhook-shaped custom JSON)** carries a ``changelog``. The
  handler syncs **only the fields listed in that changelog**, exactly like a
  real Jira webhook.

In both cases the bridge ignores events for fields it doesn't have a mapping
for.

URL
===

For both approaches, the rule sends to::

    POST https://<bridge-host>/jira2sg/<settings_name>/issue/<issue-key>

Use the ``{{issue.key}}`` smart value for the path, e.g.::

    https://bridge.example.com/jira2sg/default/issue/{{issue.key}}

Content type must be ``application/json``.

Approach 1 — Bridge-side normalization
======================================

A request opts in by setting the ``source`` sentinel; the bridge then looks up
the issue via the Jira REST API and synthesizes a webhook-shaped event. See
:func:`sg_jira.jira_automation_payload.normalize_automation_request`. Events
produced this way always trigger a full sync of the Issue (see
:ref:`jira_automation_sync_scope`).

In the Jira automation rule's *Send web request* action, set the **Custom data**
to:

.. code-block:: json

    {
        "source": "jira_project_automation",
        "user": {
            "accountId": "{{initiator.accountId}}"
        }
    }

The issue key comes from the ``{{issue.key}}`` smart value in the URL path. The
``user`` block is optional but recommended: it lets the bridge's loop-suppression
check compare ``user.accountId`` against the bridge user (see Approach 2 below).

The optional ``webhook_event`` key defaults to ``jira:issue_updated``; set it to
``jira:issue_created`` for rules that fire on issue creation.

Approach 2 — Webhook-shaped custom JSON (no bridge changes)
===========================================================

If you don't want to rely on the bridge-side normalizer at all, you can craft a
body in the automation rule that exactly mimics a Jira webhook payload. The
bridge then handles it through the same code path as a real webhook.

In the *Send web request* action, set **Web request body** to *Custom data* and
paste (this is not strict JSON — it embeds Jira smart values such as
``{{issue.asJsonString}}`` that Jira expands before sending):

.. code-block:: json
   :force:

    {
        "webhookEvent": "jira:issue_updated",
        "timestamp": {{now.toEpochMilli}},
        "user": {
            "accountId": "{{initiator.accountId}}",
            "displayName": "{{initiator.displayName}}",
            "emailAddress": "{{initiator.emailAddress}}"
        },
        "issue": {
            "id": "{{issue.id}}",
            "key": "{{issue.key}}",
            "self": "{{issue.self}}",
            "fields": {{issue.asJsonString}}
        },
        "changelog": {
            "id": "{{now.toEpochMilli}}",
            "items": [
                {{#changelog.changedFields}}
                {
                    "field": "{{name}}",
                    "fieldtype": "{{fieldType}}",
                    "fieldId": "{{fieldId}}",
                    "from": "{{fromValue}}",
                    "fromString": "{{fromString}}",
                    "to": "{{toValue}}",
                    "toString": "{{toString}}"
                }{{^last}},{{/last}}
                {{/changelog.changedFields}}
            ]
        }
    }

Notes:

* ``{{issue.asJsonString}}`` expands to the full ``fields`` object — this is the
  trick that makes the payload look like a real webhook without listing each
  field by hand.
* ``{{#changelog.changedFields}}…{{/changelog.changedFields}}`` is a Jira
  automation iteration block. ``{{^last}},{{/last}}`` inserts commas between
  items but not after the last one (otherwise the JSON is invalid).
* The ``changelog`` block is only meaningful for *field-change* triggers. For
  *issue-created* rules, drop it and set ``"webhookEvent":
  "jira:issue_created"``.
* The bridge's loop-suppression check compares ``user.accountId`` against the
  bridge user. With this approach the rule runs as the human who triggered it
  (``initiator``), so a rule on the bridge user's own change would be suppressed
  — usually what you want.

Authentication
==============

Jira automation web requests cannot sign their payloads, so anything reachable
from the public internet should sit behind a shared-secret reverse proxy or a
network allowlist. The bridge itself does not verify the caller.
