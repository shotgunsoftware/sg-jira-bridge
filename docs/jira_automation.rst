.. _jira_project_automation:

Jira Project Automation
=======================

**Sync Jira changes to Flow Production Tracking (FPTR) using project-level
Jira automation rules.**

Jira Project Automation lets a Jira project administrator send issue, comment,
and worklog changes to the Jira-to-FPTR bridge without configuring a site-wide
Jira webhook. Each rule sends a small JSON request to the bridge. The bridge
validates the request, retrieves the relevant Jira data, and passes the event
to the same Generic Syncer used by Jira webhooks.

This guide explains how to prepare the integration, configure each rule, test
its delivery, and troubleshoot common errors. Start with **full issue sync**;
add comment and worklog rules only if your project needs them.

.. warning:: Use either automation or a site webhook

   Configure **one event-delivery method per Jira project**: Jira Project
   Automation **or** a site-level Jira webhook, never both. Running both can
   sync the same change twice and cause competing updates to an FPTR entity.
   If the project already uses a Jira webhook, no automation rules are needed.

.. contents:: On this page
   :local:
   :depth: 2


How the integration works
-------------------------

When a supported event occurs in Jira, the following sequence runs:

#. A Jira automation trigger detects an issue, comment, or worklog change.
#. The rule checks its conditions, including **Sync In FPTR = True**.
#. Its **Send web request** action sends a ``POST`` request to the bridge.
#. The bridge validates the JSON, retrieves the issue or related entity from
   Jira when needed, and runs the configured Generic Syncer.
#. The syncer applies the mapping, direction, deletion, and loop-protection
   settings already defined for Jira and FPTR.

Automation and webhooks therefore produce the **same supported sync result**.
The difference is how the event reaches the bridge, not how FPTR is updated.


Before you begin
----------------

Verify the following prerequisites before creating an automation rule.

.. list-table:: Prerequisites
   :header-rows: 1
   :widths: 31 69

   * - Requirement
     - What to verify
   * - Bridge service
     - ``webapp.py`` or ``service.py`` is running. See :doc:`quickstart`.
   * - Network access
     - Jira Cloud can reach the bridge over HTTPS, and the bridge can access
       the Jira REST API. See `Network and access requirements`_.
   * - Generic Syncer
     - ``EntitiesGenericSyncer`` is configured in ``settings.py``.
       See :doc:`generic_syncer`.
   * - Jira custom fields
     - **Sync In FPTR** and the Shotgun Type, Shotgun ID, and Shotgun URL
       fields exist and appear on the applicable Jira issue screens.
   * - Test issue
     - The test issue has **Sync In FPTR** set to ``True``.
   * - Project association
     - The corresponding FPTR project's **Jira Key** field contains the
       Jira project key.
   * - Comment / worklog mappings
     - To sync comments or worklogs, ``entity_mapping`` includes ``Note``
       (comments) or ``TimeLog`` (worklogs), respectively.
   * - Deletion settings
     - To sync comment or worklog deletions, ``sync_deletion_direction``
       is enabled for the corresponding ``Note`` or ``TimeLog`` mapping.
       Deletions are ignored by default.
   * - Jira permissions
     - You can manage automation rules in the Jira project, and the Jira
       account used by the bridge can read the relevant Jira issues,
       comments, and worklogs.

.. tip::

   Use a dedicated test issue that is already associated with the correct
   FPTR project. It makes both rule failures and mapping problems easier to
   distinguish from connectivity issues.


.. _full_or_partial:

Choose which events to sync
---------------------------

.. list-table:: Supported changes
   :header-rows: 1
   :widths: 32 16 52

   * - Jira change
     - Supported
     - Behavior
   * - Issue created or updated
     - Yes
     - Synchronizes all mapped issue fields by default, or only a selected
       changed field when partial sync is configured.
   * - Comment created, updated, or deleted
     - Yes
     - Synchronizes the corresponding FPTR ``Note`` when mapped. Deleted
       replies have an additional limitation described below.
   * - Worklog created, updated, or deleted
     - Yes
     - Synchronizes the corresponding FPTR ``TimeLog`` when mapped.
   * - Issue deleted
     - No
     - Not supported through project automation or the site webhook route.

A Jira automation rule has one trigger. Create a separate rule for each
required trigger, **unless Jira offers an all-events trigger** that covers
the operations you need and returns a supported ``event_type``. Avoid
creating overlapping rules for the same change.

For issues, choose your preferred update strategy:

.. list-table:: Full versus partial issue sync
   :header-rows: 1
   :widths: 27 36 37

   * -
     - Full sync (**recommended**)
     - Partial sync (**advanced**)
   * - What is updated
     - All mapped fields on the issue.
     - Only the changed mapped field.
   * - Jira trigger
     - **Issue created** and/or **Issue updated**.
     - **Field value changed**.
   * - Maintenance
     - Simple: the rule is independent of the list of mapped fields.
     - Keep the fields watched by the rule aligned with ``field_mapping``.
   * - Trade-off
     - A Jira edit can overwrite FPTR values in other mapped fields.
     - More configuration, but fewer unrelated field updates.

For most projects, configure the full-sync rules first. Choose partial sync
when mapped fields are also edited in FPTR and should not be overwritten by
unrelated Jira edits. See `Optional: partial issue sync`_ for the exact setup.


Configure the shared web request
--------------------------------

Every automation rule uses the same endpoint, HTTP method, header, and request
body type. Only the trigger and JSON payload change between rule types.

#. Open the Jira project and select **Project settings > Automation**.
#. Select **Create rule**, then choose the trigger for the event to sync.
#. Add **Issue fields condition** and set **Sync In FPTR** to ``True``.
   This prevents requests for issues that are not opted in to FPTR sync.
#. Add the **Send web request** action.
#. Enter the values below, then paste the payload for your chosen rule from
   the next section.

.. list-table:: Send web request settings
   :header-rows: 1
   :widths: 30 70

   * - Setting
     - Value
   * - Web request URL
     - ``https://<bridge-host>/jira2sg/<settings_name>/issue/{{issue.key}}``
   * - HTTP method
     - ``POST``
   * - Headers
     - ``Content-Type: application/json``
   * - Web request body
     - **Custom data** (not **Issue data**)
   * - Custom data
     - The JSON example for the relevant rule in this guide.

For example, if your bridge is hosted at ``bridge.example.com`` and your
Generic Syncer is named ``entities``, the URL is:

.. code-block:: text

   https://bridge.example.com/jira2sg/entities/issue/{{issue.key}}

Replace ``<bridge-host>`` with the actual bridge host and
``<settings_name>`` with the Generic Syncer settings name, commonly
``entities``. Keep ``{{issue.key}}`` unchanged: Jira replaces it with the
issue key when the rule executes.

.. important::

   In all JSON examples, keep the Jira smart values inside double curly
   braces exactly as shown. In particular,
   ``{{initiator.accountId}}`` identifies who caused the change and is
   **required** for the bridge's loop protection.


Create the event rules
----------------------

Create only the rules relevant to your project. After configuring each rule,
save it, give it a recognizable name, and enable it when you are ready to
test. The **Sync In FPTR** condition and web-request settings from the
previous section apply to **every** example below.

Full issue sync
~~~~~~~~~~~~~~~

**Use for:** a new issue or an update to an existing issue.

Create an **Issue created** rule and, if ongoing updates should sync, a
separate **Issue updated** rule. Both use the following **Custom data**:

.. code-block:: json

   {
     "source": "jira_project_automation",
     "actor": {
       "accountId": "{{initiator.accountId}}"
     }
   }

No ``event_type`` or ``field_change`` property is needed. The bridge reads
the issue and synchronizes all mapped issue fields according to its settings.

.. figure:: _static/full_sync.png
   :alt: Jira Send web request action configured for a full issue sync, showing POST, Custom data, and the issue-key URL.
   :align: center
   :width: 85%

   **Full issue sync:** configure the shared endpoint and paste the minimal
   JSON payload above. The screenshot focuses on the web request action;
   remember to add the **Sync In FPTR** condition to the rule.

.. note::

   Do not combine **Issue updated** full sync with a **Field value changed**
   partial-sync rule for the same edits. That would send overlapping events.
   A valid hybrid is **Issue created** (full sync) plus **Field value changed**
   (partial sync) for later edits.


Comment sync
~~~~~~~~~~~~

**Use for:** a comment added, edited, or deleted on an issue.

Select the Jira comment trigger(s) available in your project, such as
**All comments**, **Work item comment edited**, or **Work item comment
deleted**. Depending on your Jira version, a broad comment trigger may cover
several operations; confirm its behavior in the automation audit log.

For a comment rule, paste:

.. code-block:: json

   {
     "source": "jira_project_automation",
     "actor": {
       "accountId": "{{initiator.accountId}}"
     },
     "event_type": "{{eventType}}",
     "id": "{{comment.id}}"
   }

The bridge accepts these comment event types:

- ``comment_created``
- ``comment_updated``
- ``comment_deleted``

``{{comment.id}}`` is the Jira comment ID; you do not have to look it up.
For non-deletion events, the bridge reads the current comment from Jira.

.. figure:: _static/comment_sync.png
   :alt: Jira comment trigger choices and a Send web request configuration panel.
   :align: center
   :width: 98%

   **Comment rule configuration:** choose the relevant comment trigger, then
   configure the shared request settings. **Use the comment JSON shown above,**
   not the worklog-specific fields visible in this reference screenshot.

.. important:: Comment payload field names

   The request key is ``event_type`` (with an underscore), **not**
   ``eventType``. The **value** can be ``{{eventType}}`` if Jira resolves that
   smart value to one of the supported names. If it does not, create one
   rule per event and use the corresponding literal value, for example
   ``"event_type": "comment_deleted"`` in a comment-deleted rule.

.. note:: Deleted comment replies

   With project automation, Jira may no longer provide a deleted reply's
   parent-comment relationship. The bridge therefore cannot always identify
   it as a reply, and that reply can remain in FPTR. Site webhooks preserve
   the information needed to handle this case.


Worklog sync
~~~~~~~~~~~~

**Use for:** time logged, modified, or deleted on an issue.

Choose **Work logged** (covering **All worklog operations**, if available)
or create separate event-specific worklog rules. Paste this minimal payload:

.. code-block:: json

   {
     "source": "jira_project_automation",
     "actor": {
       "accountId": "{{initiator.accountId}}"
     },
     "event_type": "{{eventType}}",
     "id": "{{worklog.id}}"
   }

The bridge accepts these worklog event types:

- ``worklog_created``
- ``worklog_updated``
- ``worklog_deleted``

For non-deletion events, the bridge retrieves the authoritative worklog
from Jira. You may also include accepted worklog snapshot properties,
``timeSpentSeconds``, ``timeSpent``, and ``comment``, where needed for a
deleted worklog. Such optional values must be correctly JSON-escaped if
they contain user-entered text. Here, ``comment`` means the **worklog note**,
not a separate Jira issue comment.

.. figure:: _static/worklog_sync.png
   :alt: Jira Work logged trigger and Send web request action for a worklog automation rule.
   :align: center
   :width: 98%

   **Worklog rule configuration:** use the Work logged trigger and the
   common POST endpoint. The screenshot illustrates optional snapshot
   properties. Use ``event_type`` (underscore) in the actual payload,
   as shown above, rather than the ``eventType`` key pictured.

.. tip::

   If ``{{eventType}}`` is not expanded to a supported event name in your
   Jira environment, use a separate rule for each operation and enter its
   literal event type. An **All worklog operations** rule should be used
   only when its event type can be distinguished reliably.


.. _advanced_partial_sync:

Optional: partial issue sync
----------------------------

Partial sync sends a single changed field rather than re-synchronizing all
mapped fields. It is useful when people edit the same entities in both Jira
and FPTR, or when issues contain many mapped fields.

#. Create a new automation rule with the **Field value changed** trigger.
#. Select the Jira fields to watch (for example, Summary, Status, Priority,
   Labels, or your mapped custom fields).
#. Add **Issue fields condition > Sync In FPTR = True**.
#. Add **Send web request** with the same URL, ``POST`` method,
   ``Content-Type`` header, and **Custom data** body type.
#. Paste this JSON:

.. code-block:: json

   {
     "source": "jira_project_automation",
     "actor": {
       "accountId": "{{initiator.accountId}}"
     },
     "field_change": {
       "fieldId": "{{fieldChange.fieldId}}",
       "fromString": "{{fieldChange.fromString}}",
       "toString": "{{fieldChange.toString}}"
     }
   }

``fieldId`` is required. ``fromString`` and ``toString`` are optional,
informational values; the bridge reads the actual current field value from
Jira. They can be empty if the user clears a field. You may also specify a
literal ID, such as ``"fieldId": "summary"``, when a rule watches one field.
Only fields configured in ``field_mapping`` are synchronized.

.. figure:: _static/field_sync.png
   :alt: Jira Field value changed automation showing selected fields and a Send web request action with field_change JSON.
   :align: center
   :width: 98%

   **Partial field sync:** the Field value changed trigger sends the
   changed field's ID. Keep the trigger's watched fields aligned with the
   bridge's ``field_mapping``.

.. warning::

   **Partial sync requires the Field value changed trigger.** Do not use
   **Issue updated** with ``{{fieldChange.fieldId}}``: Jira may leave that
   smart value empty, causing the bridge to reject the request. Also avoid
   ``{{#changelog.changedFields}}`` in project automation; it is not
   populated for this workflow.


Enable and verify the rules
---------------------------

Test the rules before relying on them for production synchronization.

#. **Save and enable** the rule in Jira.
#. Open a test issue that belongs to the linked project and has
   **Sync In FPTR = True**.
#. Make a change matching the rule's trigger: edit an issue, add a comment,
   log time, or change a watched field.
#. Open **Project settings > Automation**, select the rule, and inspect its
   **Audit log**. Verify that the trigger and condition ran and that the
   web request was sent.
#. If Jira reports **HTTP 200**, the bridge has received the request.
   Check the **bridge application log** and the corresponding FPTR entity to
   confirm that the change was actually applied.
#. Repeat for update and deletion scenarios when those are enabled, and
   verify that unflagged issues do not sync.

.. important::

   **HTTP 200 confirms request receipt, not completion of the FPTR sync.**
   The bridge log is the source of truth for mapping, synchronization,
   ignored events, and downstream errors.

Suggested checks for the first rollout:

.. list-table:: Acceptance checks
   :header-rows: 1
   :widths: 37 63

   * - Test
     - Expected result
   * - Create or edit a flagged issue
     - Mapped issue fields are created or updated in FPTR.
   * - Edit a field watched by partial sync
     - Only that mapped field is synchronized.
   * - Create or edit a comment
     - A corresponding FPTR ``Note`` is created or updated.
   * - Log or edit time
     - A corresponding FPTR ``TimeLog`` is created or updated.
   * - Delete a comment or worklog
     - The mapped entity is deleted only when deletion sync is enabled,
       subject to the deleted-comment-replies limitation.
   * - Edit an unflagged issue
     - The rule's condition prevents synchronization.
   * - Change Jira as the bridge's own user
     - The bridge ignores the self-generated event to prevent loops.


Troubleshooting
---------------

First check the **Jira automation audit log**, then the **bridge log**.
An HTTP ``400`` generally means that the JSON or smart values were rejected;
``500`` indicates a server-side failure and may include problems fetching
Jira data. A connection failure may prevent Jira from obtaining any HTTP
response at all.

.. list-table:: Common failures and corrective actions
   :header-rows: 1
   :widths: 43 57

   * - Error or symptom
     - Recommended action
   * - No request appears in the audit log
     - Confirm the rule is enabled, its trigger matches the test change,
       and **Sync In FPTR = True** is satisfied.
   * - Connection timeout or unreachable URL
     - Confirm the bridge is running, the public HTTPS address and route
       are correct, and firewall or ingress rules permit Jira traffic.
   * - ``actor is required`` or ``actor.accountId is empty``
     - Include ``"actor": {"accountId": "{{initiator.accountId}}"}``.
       Use an event caused by an actual user, not an unsupported scheduled
       context without an initiator.
   * - ``contains an unexpanded Jira smart value``
     - Check smart-value spelling and that the trigger exposes the value.
       For instance, ``{{comment.id}}`` belongs in a comment rule.
   * - ``has unexpected keys``
     - Use the exact property names in this guide and remove unsupported
       fields. In particular, use ``event_type`` rather than ``eventType``.
   * - ``Unsupported event_type``
     - Ensure comment rules use ``comment_created``, ``comment_updated``,
       or ``comment_deleted``; worklog rules use the equivalent
       ``worklog_*`` values. Issue full-sync rules omit this property.
   * - Jira issue or related entity not found
     - Confirm the URL ends with ``{{issue.key}}`` and the issue exists.
       Deleted comments and worklogs may no longer be retrievable from Jira.
   * - ``FPTR Note`` or ``FPTR TimeLog is not configured for syncing``
     - Add ``Note`` or ``TimeLog`` to ``entity_mapping``.
   * - ``has not been flagged as synced``
     - Enable **Sync In FPTR** on the issue.
   * - ``sync direction ... only sync from FPTR to Jira``
     - Set ``sync_direction`` to ``both_way`` or ``jira_to_sg`` for the
       relevant entity mapping.
   * - ``deletion is disabled``
     - Configure ``sync_deletion_direction`` for ``Note`` or ``TimeLog``.
   * - ``created by the bridge user``
     - Expected behavior. The bridge suppresses its own events to avoid
       synchronization loops.
   * - HTTP 200, but no change in FPTR
     - Review bridge logs, **Sync In FPTR**, project linking,
       ``field_mapping``, ``entity_mapping``, and sync direction.


Network and access requirements
-------------------------------

Jira Cloud runs automation requests from Atlassian's infrastructure, not from
your browser. Make sure the bridge endpoint is reachable from Jira over
**HTTPS**. If the service is behind a firewall, use current Atlassian
outbound IP guidance to configure the appropriate allowlist.

The bridge also needs outbound access to Jira's REST API so it can retrieve
current issue, comment, and worklog data. Protect the public endpoint using
the access controls appropriate to your bridge deployment; do not add API
credentials or secrets to the JSON examples in this guide.

For a bridge running locally or behind a private network, see the
**Testing on a Machine Not Accessible to Jira** section of :doc:`debugging`.


.. _automation_vs_webhooks:

Automation compared with site webhooks
--------------------------------------

Both methods use the same Generic Syncer and mapping rules, but they differ
operationally.

.. list-table:: Automation versus site webhooks
   :header-rows: 1
   :widths: 25 37 38

   * - Consideration
     - Jira Project Automation
     - Jira site webhook
   * - Setup permissions
     - Project administrator; configured per project.
     - Jira administrator; configured at site level.
   * - Setup effort
     - One rule per trigger (or a supported combined trigger).
     - A single webhook can cover selected event types.
   * - Filtering
     - Automation triggers and conditions.
     - Webhook JQL filtering.
   * - Issue field updates
     - Full sync by default; optional explicit per-field rule.
     - Changed fields are supplied automatically by the webhook event.
   * - Debugging
     - Per-rule audit log plus the bridge log.
     - Webhook delivery details plus the bridge log.
   * - Jira API reads
     - The bridge fetches current data for each event.
     - Webhook payloads already include the relevant event data.
   * - Deleted comment replies
     - Parent/reply relationship may be unavailable after deletion.
     - Reply information is available in the webhook event.
   * - Usage limits
     - Subject to the automation execution limits of the Jira plan.
     - Not subject to Jira automation-rule execution quotas.

Choose **automation** if you manage only a project, need rule-level
conditions, or want a clear audit trail per trigger. Choose a **site webhook**
if an administrator manages many Jira projects centrally or you need
out-of-the-box changed-field handling.


Implementation notes for maintainers
------------------------------------

This section is intended for developers maintaining the Jira-to-FPTR bridge.
Administrators can complete the setup without it.

- **Normalization:** ``webapp.py`` recognizes a request with
  ``"source": "jira_project_automation"`` on the ``jira2sg`` route.
  ``sg_jira.jira_automation_payload.normalize_automation_request`` converts
  it into the event shape produced by a site webhook. Other request bodies
  are not modified.
- **Issue events:** issue creation and update use the normalized
  ``jira:issue_updated`` event. Without ``field_change``, the bridge
  triggers full mapped-field sync; with ``field_change``, it generates a
  one-field changelog entry.
- **Related entities:** comment and worklog events require ``event_type``
  and ``id``. When available, current data comes from
  ``JiraSession.comment_as_webhook_entity`` or
  ``JiraSession.worklog_as_webhook_entity``. Optional request values can
  supplement data that Jira no longer exposes after deletion.
- **Validation:** unknown keys, unresolved smart values, and a missing
  ``actor.accountId`` generate HTTP ``400`` responses. Jira API and other
  server-side failures can generate HTTP ``500`` responses.
- **Tests:** ``tests/test_jira_automation_payload.py`` verifies the payload
  normalizer; ``tests/test_jira_automation_parity.py`` verifies parity with
  webhook processing through the Generic Syncer handler.
