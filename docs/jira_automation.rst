.. _jira_project_automation:

Jira Project Automation
#######################

Jira Project Automation lets a project administrator sync Jira → Flow Production
Tracking (FPTR) with **automation rules**, instead of a site-level Jira webhook.
Each rule sends a small JSON message to the bridge, and the bridge handles it
exactly like a webhook event.

.. important::

   **Automation is an alternative to site webhooks. Use one or the other for a
   Jira project, never both.** Running both syncs every change twice and can make
   the two syncs race on the same FPTR entity. If you already set up the
   :ref:`Jira Webhook <Jira Webhook>`, you don't need anything on this page.

Automation and webhooks give the same sync results. Both feed the same Generic
Syncer, with the same settings, the same *Sync In FPTR* flag and the same loop
protection. They differ in who sets them up, how many pieces you configure and a
few trade-offs, which are listed in :ref:`automation_vs_webhooks` so you can pick
the one that suits you.

.. contents::
   :local:
   :depth: 2

Before you start
****************

Check all of these before you create a rule. Most "nothing happened" problems come
from one of them.

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Requirement
     - How to check
   * - The bridge is running
     - ``webapp.py`` or ``service.py`` is up. See :doc:`quickstart`.
   * - Jira can reach the bridge URL
     - Same as for a webhook: see :ref:`Jira Webhook` in the quickstart, and
       `Network access`_ below.
   * - The Generic Syncer is configured
     - ``EntitiesGenericSyncer`` is in ``settings.py``. See :doc:`generic_syncer`.
   * - The Jira fields exist
     - *Sync In FPTR* and the Shotgun Type / ID / URL fields exist and are on the
       Issue screen. See :ref:`Jira Configuration <entity-sync-jira-config>`.
   * - The Issue is flagged *Sync In FPTR*
     - On a test Issue, *Sync In FPTR* is ``True``.
   * - The Jira project is linked to an FPTR project
     - The FPTR project's *Jira Key* field holds the Jira project key.
   * - Comments and worklogs are mapped (only if you sync them)
     - ``Note`` (comments) and ``TimeLog`` (worklogs) have an entry in
       ``entity_mapping``. Without it, comment or worklog events are rejected.
   * - Deletions are enabled (only if you sync them)
     - ``sync_deletion_direction`` is set on the ``Note`` or ``TimeLog`` entry.
       Deletions are ignored by default.

What is supported
*****************

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Jira change
     - Supported
     - Notes
   * - Issue created or updated
     - Yes
     - Full sync, or only the field that changed. See :ref:`full_or_partial`.
   * - Comment created, updated, deleted
     - Yes
     - Includes replies (see the deleted replies limitation in the comparison below).
   * - Worklog created, updated, deleted
     - Yes
     -
   * - Issue deleted
     - No
     - Not supported with webhooks either.

.. _automation_vs_webhooks:

Automation or webhooks?
=======================

For every supported change, automation and webhooks end in the **same FPTR
result**. The differences are in setup and operations:

.. list-table::
   :header-rows: 1
   :widths: 22 39 39

   * -
     - Jira Project Automation
     - Site webhook
   * - Who sets it up
     - A **project administrator**, per project.
     - A **Jira administrator**, once for the site.
   * - What you configure
     - One rule per Jira trigger (Issue, comment, worklog), each with a short
       message to copy and paste.
     - One webhook for all events.
   * - Which changes are sent
     - What the rule's trigger and conditions allow. A change with no matching
       trigger in your Jira cannot be synced.
     - Every event of the types you ticked, filtered by JQL.
   * - Field-level sync
     - Full sync of all mapped fields (default), or a rule per changed field
       (:ref:`advanced <advanced_partial_sync>`).
     - Automatic: Jira says which fields changed, and only those are synced.
   * - Filtering
     - Rule **conditions** (Sync In FPTR, issue type, status...).
     - JQL.
   * - Troubleshooting
     - Each rule has an **audit log** with the request and the response.
     - Jira's webhook delivery details, plus the bridge log.
   * - Extra Jira calls
     - The bridge reads the Issue, comment or worklog back from Jira on each event.
     - The event already carries the data.
   * - Deleted comment replies
     - **Not recognized as replies**: the reply stays in FPTR. Jira can no longer
       say which comment it answered.
     - Recognized and removed.
   * - Limits
     - Jira Cloud plans can limit how often automation rules run. Check your
       plan's automation limits.
     - None specific to webhooks.

**Choose automation when** you are a project admin without Jira admin rights, you
want to restrict the sync per project with conditions, or you like seeing every
request in an audit log.

**Choose a webhook when** you are a Jira admin, many projects should sync the same
way, or you want per-field syncing without writing a rule per field.

.. _full_or_partial:

Full sync or field change?
==========================

For Issues you pick **what the rule sends**, not just when it fires:

.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * -
     - Full sync (recommended)
     - Partial sync (*Field value changed*)
   * - What is synced
     - **All** mapped fields of the Issue, on every run.
     - **Only** the field that changed.
   * - Rules to maintain
     - One.
     - One per set of fields you watch.
   * - Watch out for
     - A Jira edit overwrites FPTR values for **all** mapped fields, even ones you
       did not touch in Jira. More API calls on large Issues.
     - You must keep the rule's field list up to date.

**Start with full sync.** It is one rule, has nothing to keep in step with your
field mapping, and it is the right default for most pipelines.

**Switch to partial sync** if people also edit those fields in FPTR and a Jira edit
should not overwrite them, or if Issues are large and busy. Partial sync only works
with the **Field value changed** trigger.

**Do you need both?** Usually not: a full sync rule already covers changes. If you
want a webhook-like setup, use a full sync rule only for **Issue created**
(to fill in everything the first time) and a partial rule for **Field value
changed**. Do not use full sync on *Issue updated* together with a partial rule:
every edit would sync twice.

Quick setup
***********

This sets up the recommended full sync, plus comments and worklogs. You create one
rule per row you need. Each rule has the same four parts.

.. todo::

   Screenshot ``jira_automation_rule_overview.png``: a finished rule in Jira
   (trigger, *Sync In FPTR* condition and *Send web request* action).

1. Create the rule
==================

1. In your project open **Project settings → Automation → Create rule**.
2. Choose the **trigger** from the table below.

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - To sync...
     - Trigger
   * - A new Issue, or a changed Issue (full sync)
     - **Issue created** and/or **Issue updated**
   * - A comment
     - The comment triggers (added, edited, deleted)
   * - A worklog
     - The work log triggers (logged, updated, deleted)

A Jira rule has a single trigger, so you create one rule per trigger.

2. Add the condition
====================

Add a condition: **Issue fields condition → Sync In FPTR equals True**. This keeps
Issues that should not be synced from reaching the bridge.

Optionally add a **smart values condition** so the rule does not run for the
bridge's own Jira user, to avoid sync loops. The bridge also protects against loops
by itself.

.. todo::

   Screenshot ``jira_automation_condition.png``: the *Sync In FPTR equals True*
   condition.

3. Add the *Send web request* action
====================================

Add the action **Send web request** and set:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Setting
     - Value
   * - Web request URL
     - ``https://<bridge-host>/jira2sg/<settings_name>/issue/{{issue.key}}``
   * - HTTP method
     - **POST**
   * - Headers
     - ``Content-Type: application/json``
   * - Web request body
     - **Custom data** (not *Issue data*)

Replace ``<bridge-host>`` with the address of the machine running the bridge, and
``<settings_name>`` with your Generic Syncer settings name (often ``entities``).
Leave ``{{issue.key}}`` exactly as written: Jira fills in the Issue key when the
rule runs.

.. todo::

   Screenshot ``jira_automation_send_web_request.png``: the *Send web request*
   action with the URL, method and *Custom data* body type.

4. Paste the Custom data
========================

Paste the message that matches the rule. Do not change the ``{{...}}`` parts.

**Issue: full sync** (Issue created / Issue updated rules)::

    {
        "source": "jira_project_automation",
        "actor": {"accountId": "{{initiator.accountId}}"}
    }

**Comment** (comment rules): ``{{eventType}}`` tells the bridge whether the
comment was created, updated or deleted::

    {
        "source": "jira_project_automation",
        "actor": {"accountId": "{{initiator.accountId}}"},
        "event_type": "{{eventType}}",
        "id": "{{comment.id}}"
    }

**Worklog** (worklog rules)::

    {
        "source": "jira_project_automation",
        "actor": {"accountId": "{{initiator.accountId}}"},
        "event_type": "{{eventType}}",
        "id": "{{worklog.id}}"
    }

You never look up an id in Jira. Jira replaces each ``{{...}}`` when the rule runs.
``{{initiator.accountId}}`` is who made the change; it is how the bridge ignores
changes it made itself, so it is required.

.. note::

   Comment rules may also send ``"body": "{{comment.body}}"`` and worklog rules
   ``"comment"``, ``"timeSpentSeconds"`` and ``"timeSpent"``. They are optional:
   the bridge always reads the real values from Jira. They are only used when
   Jira can no longer be asked, that is when a comment or worklog is deleted. On a
   worklog rule, ``comment`` is the worklog note, not a Jira comment.

5. Turn it on and test it
=========================

1. Turn the rule on.
2. In Jira, change a test Issue that has *Sync In FPTR* set to ``True``.
3. Open the rule's **audit log**. A successful run shows **HTTP 200**, which means
   the bridge *received* the request. Whether the sync happened is in the bridge
   log.

.. todo::

   Screenshot ``jira_automation_audit_log.png``: the audit log of a successful
   run, showing the *Send web request* result.

If it did not work
------------------

The audit log shows what the bridge said. A message starting with **400** is a
mistake in the rule; **500** means the bridge could not reach Jira (try again, and
check the bridge log).

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Message
     - What to do
   * - ``actor is required`` / ``actor.accountId is empty``
     - Add the ``actor`` line from the message above. The rule must be run by a
       user, not by a schedule.
   * - ``... contains an unexpanded Jira smart value``
     - A ``{{...}}`` was not replaced. Re-check the spelling against this page and
       the rule's trigger (for example ``{{comment.id}}`` only works in a comment
       rule).
   * - ``... has unexpected keys``
     - The message has a line this page does not list. Remove it.
   * - ``Unsupported event_type``
     - ``event_type`` is only for comment and worklog rules. Remove it from Issue
       rules.
   * - ``Jira Issue 'X' was not found`` / ``... was not found on Issue``
     - The URL must end with ``{{issue.key}}``, and the comment or worklog must
       still exist.
   * - Bridge log: ``FPTR Note`` / ``FPTR TimeLog is not configured for syncing``
     - Add a ``Note`` or ``TimeLog`` entry to ``entity_mapping``.
   * - Bridge log: ``has not been flagged as synced``
     - Set *Sync In FPTR* to ``True`` on the Issue.
   * - Bridge log: ``sync direction ... only sync from FPTR to Jira``
     - Set ``sync_direction`` to ``both_way`` or ``jira_to_sg`` for that entity.
   * - Bridge log: ``deletion is disabled``
     - Set ``sync_deletion_direction`` on the ``Note`` or ``TimeLog`` entry.
   * - Bridge log: ``created by the bridge user``
     - Expected: the bridge ignores its own changes.

.. _advanced_partial_sync:

Advanced: partial sync (optional)
*********************************

Use this only if you decided on partial sync in :ref:`full_or_partial`. Create a
rule with the trigger **Field value changed**, choose the fields to watch, and use
the same condition and *Send web request* action as in `Quick setup`_, with this
Custom data::

    {
        "source": "jira_project_automation",
        "actor": {"accountId": "{{initiator.accountId}}"},
        "field_change": {
            "fieldId": "{{fieldChange.fieldId}}",
            "fromString": "{{fieldChange.fromString}}",
            "toString": "{{fieldChange.toString}}"
        }
    }

.. warning::

   Partial sync **must** use the **Field value changed** trigger. Do not use
   *Issue updated* (a work item update): Jira does not guarantee that it provides
   the information about which field changed, so ``{{fieldChange...}}`` can come
   out empty and the bridge rejects the request. Use *Issue updated* only for
   full sync, which does not need that information.

* ``fieldId`` is required. If a rule watches a single field you can type its id
  instead, for example ``"fieldId": "summary"``.
* ``fromString`` and ``toString`` are optional and informational (the bridge reads
  the new value from Jira). They may be empty when a value is cleared. ``field``,
  the field's name, is optional too.
* Do **not** use ``{{#changelog.changedFields}}`` in Project Automation: that block
  is empty there.
* Only fields mapped in ``field_mapping`` are synced; a change to any other field
  is ignored.

.. todo::

   Screenshot ``jira_automation_field_value_changed.png``: the *Field value
   changed* trigger with the watched fields selected.

Network access
**************

Same requirements as the :ref:`Jira Webhook <Jira Webhook>`:

* Jira Cloud sends the request from Atlassian's servers, so the bridge URL must be
  reachable from the internet (or your firewall must allow Atlassian's published IP
  ranges). Use HTTPS.
* The bridge must also be able to reach the Jira API, to read back the Issue,
  comment or worklog.

For a local test setup, see the *Testing on a Machine Not Accessible to Jira*
section of :doc:`debugging`.

For developers
**************

Everything above is enough to use the feature. This section is for people changing
it.

* **Flow.** ``webapp.py`` passes any ``jira2sg`` body with
  ``"source": "jira_project_automation"`` to
  :func:`sg_jira.jira_automation_payload.normalize_automation_request`, which turns
  it into the event a site webhook would have sent. Other bodies are untouched.
  The event then goes through the usual
  :class:`~sg_jira.handlers.entities_generic_handler.EntitiesGenericHandler`.
* **Issue rules**: no ``event_type``. With ``field_change`` the event carries one
  changelog item (partial sync). Without it, the changelog item is the *Sync In FPTR*
  field, which makes the handler sync every mapped field. Created and updated Issues
  are handled identically, so the event is always ``jira:issue_updated``.
* **Comment and worklog rules**: ``event_type`` is one of ``comment_created``,
  ``comment_updated``, ``comment_deleted``, ``worklog_created``,
  ``worklog_updated``, ``worklog_deleted`` and ``id`` is required. The entity is
  read back from Jira
  (:meth:`~sg_jira.jira_session.JiraSession.comment_as_webhook_entity`,
  :meth:`~sg_jira.jira_session.JiraSession.worklog_as_webhook_entity`); what the
  rule sent only fills in what Jira cannot say.
* **Strict input.** Unknown keys, unexpanded smart values and a missing
  ``actor.accountId`` are rejected with HTTP 400. Jira errors other than "not
  found" propagate (HTTP 500).
* **Tests.** ``tests/test_jira_automation_payload.py`` covers the normalizer;
  ``tests/test_jira_automation_parity.py`` sends automation bodies through the real
  handler and expects the same outcome as the webhook tests.
