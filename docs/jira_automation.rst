.. _jira_project_automation:

Jira Project Automation
#######################

Jira **Project Automation** lets a Jira *project* administrator sync Issues to
Flow Production Tracking (FPTR).

When an automation rule runs:

1. Jira sends a request to the Jira–FPTR bridge.
2. The bridge reads the Jira Issue.
3. The bridge syncs the configured information to FPTR.

`Set up an automation rule`_ below is the standard path, and all most projects
need. It performs a **full sync**: every mapped field on the Issue is sent to
FPTR whenever the rule runs. If you specifically need a single-field or
changed-field sync, see :ref:`jira_automation_advanced` at the end of the page.

An alternative to the Jira webhook
**********************************

There are two ways for Jira to notify the bridge that an Issue changed: a
site-level **webhook** (see :ref:`Jira Webhook`) or **project automation
rules**. They do the same job, so pick one per Jira project.

.. warning::
   Do not run both for the same project. Every change would reach the bridge
   twice and be synced twice, and the two syncs can overlap on the same entity.

**Prefer a webhook if you can create one.** It needs Jira site-administrator
rights, and in return Jira does the work: one webhook covers the whole site,
Jira builds the payload, only the fields that actually changed are synced, and
comment and worklog changes are reported as they happen.

**Use automation rules when you only have project-administrator rights.** You
add a rule, and the JSON body below, to each project you want synced. Every run
is a full sync: the bridge re-reads the Issue and re-writes every mapped field.
Comment and worklog changes are not sent on their own — they are picked up by
the next full sync of that Issue.

Before you start
****************

Confirm all the following requirements before creating the automation rule.
If one of these requirements is missing, Jira may report that the request was
successful, but the bridge may skip the Issue without changing anything in
FPTR.

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Requirement
     - How to check
   * - The **bridge is running**
     - Open the bridge URL, for example ``https://<bridge-host>/`` See :ref:`quickstart` to setup instructions.
   * - **Jira can reach the bridge URL**
     - The bridge must be reachable from Jira. If Jira webhooks already work
       with this bridge, automation rules should work too. See
       :ref:`Jira Webhook` and `Network access`_.
   * - The **Generic Syncer** is configured.
     - In ``settings.py`` confirm that a ``SYNC`` entry uses
       ``sg_jira.EntitiesGenericSyncer``. The entry name, often ``entities`` is the *settings
       name* used in the automation URL. See :doc:`generic_syncer`.
   * - The **Sync In FPTR field is on the Issue screen**
     - Open any Issue in the project and look for *Sync In FPTR*. If it is
       missing, the bridge rejects every event for this project and issue
       type — see :ref:`Jira Configuration <entity-sync-jira-config>`.
   * - One **test Issue has Sync In FPTR = True**
     - The bridge skips Issues where this is ``False`` or empty. Set it on one
       Issue now, so you have something to test the rule with.
   * - The Jira project is **linked to an FPTR project**
     - The FPTR Project's *Jira Key* field holds the Jira project key
       (e.g. ``PROJ``).
   * - The **issue type is set up for syncing**
     - It is listed in the Generic Syncer settings, and its sync direction
       allows Jira → FPTR.
   * - You can create automation rules in the Jira project
     - *Project settings → Automation*.

What is supported
*****************

The table below covers what an automation rule can send to the bridge. Updates
that originate in FPTR reach Jira through a separate mechanism, the FPTR Event
Daemon and its ``sg_jira_event_trigger`` plugin — see :doc:`generic_syncer`.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Item
     - Support
   * - Jira resource
     - **Issues only.** A rule triggered by a comment or a worklog is not
       supported.
   * - Events
     - Issue updated (the default) and issue created.
   * - Fields synced
     - **Full sync** — every field mapped for that issue type in the Generic
       Syncer settings, plus the Issue's comments (FPTR Notes). Fields with no
       mapping are ignored.
   * - Worklogs / TimeLogs
     - Only synced if ``TimeLog`` is present in the Generic Syncer's
       ``entity_mapping``. It is **not** in the default configuration, so out
       of the box worklogs are not synced.

Set up an automation rule
*************************

1. In Jira, go to **Project settings → Automation → Create rule**.

2. Choose a trigger — typically **Field value changed** (pick the fields you
   care about) or **Issue created**.

   .. note::
      The fields you select in the trigger decide when the automation runs.
      They do not decide which fields are sent to FPTR.
      For example, even if the rule runs only when Status changes,
      the bridge still syncs all mapped fields.
      To limit which fields can sync, change ``field_mapping``
      in ``settings.py``; to sync only what changed, see
      :ref:`jira_automation_advanced`.

3. *(Recommended)* Add a **Condition → Issue fields condition**:
   *Sync In FPTR* **equals** ``True``. The bridge enforces this anyway; the
   condition just avoids pointless web requests.

4. Add the action **Send web request** and fill it in:

   .. list-table::
      :widths: 30 70

      * - **Web request URL**
        - ``https://<bridge-host>/jira2sg/<settings_name>/issue/{{issue.key}}``
      * - **HTTP method**
        - ``POST``
      * - **Web request body**
        - ``Custom data``
      * - **Headers**
        - ``Content-Type: application/json``

   Replace ``<bridge-host>`` and ``<settings_name>`` with your own values, and
   leave ``{{issue.key}}`` exactly as written — Jira fills it in. For example::

       https://bridge.example.com/jira2sg/entities/issue/{{issue.key}}

   .. figure:: _static/jira_automation_send_web_request.png

      The *Send web request* action. **Web request body** must be set to
      *Custom data*.

5. Paste this into **Custom data**:

   .. code-block:: json

       {
           "source": "jira_project_automation",
           "user": {
               "accountId": "{{initiator.accountId}}"
           }
       }

   ``source`` is what tells the bridge to read the Issue and sync it.

   Always include the ``user`` block. The rule fires on every change to the
   Issue, including the ones the bridge itself makes when syncing FPTR → Jira.
   ``user`` reports who triggered the rule, which is how the bridge tells those
   apart and skips its own. Without it, the bridge cannot, so it sends its own
   writes back to FPTR. That is wasted work rather than an endless loop — FPTR,
   in turn, ignores changes made by the bridge user.

6. **For an issue-created rule only**, add ``webhook_event``:

   .. code-block:: json

       {
           "source": "jira_project_automation",
           "webhook_event": "jira:issue_created",
           "user": {
               "accountId": "{{initiator.accountId}}"
           }
       }

   The only accepted values are ``jira:issue_updated`` (the default, used when
   the key is omitted) and ``jira:issue_created``.

7. Turn the rule on and change a field on a test issue. Check the rule's
   **Audit log** in Jira for the HTTP response, and the bridge log for the
   sync itself. A ``200`` in the audit log only means the bridge *received* the
   request; it does not confirm that the Issue synced.

If the rule reports success but nothing changes in FPTR, the bridge received
the request and then skipped the sync. Re-check `Before you start`_ — a missing
project link, *Sync In FPTR* not set to ``True``, or an issue type that isn't
configured are the usual causes. The bridge logs the exact reason at debug
level; see :doc:`debugging`.

Network access
**************

An automation rule reaches the bridge exactly the way a Jira webhook does, so
the network requirements are the same:

* The bridge URL must be reachable from Jira over HTTPS. For Jira Cloud that
  means reachable from Atlassian's published outbound IP ranges; for Jira Data
  Center, from your Jira nodes. Whoever opened the firewall or configured the
  reverse proxy for :ref:`Jira Webhook` has already done this work — if
  webhooks to this bridge work, automation rules will too.
* If the bridge sits behind a reverse proxy, the automation rule must use the
  proxy's public URL, and the proxy must forward ``POST`` requests with a JSON
  body to the bridge.
* The bridge also needs outbound access to your Jira site, because it reads the
  Issue back from Jira when the rule fires.
* Testing against a bridge Jira can't reach (a laptop, a private network) won't
  work. See the *Testing on a Machine Not Accessible to Jira* section of
  :doc:`debugging`.

.. _jira_automation_advanced:

Advanced — sync only the changed fields
***************************************

Skip this section unless you specifically need field-change scope instead of a
full sync.

.. note::
    A regular Jira webhook already does this, with no hand-written JSON: Jira
    builds the payload itself and the bridge syncs only the fields in its
    changelog. **If you have Jira site-administrator access, set up a webhook
    instead** — see :ref:`Jira Webhook`. Use the rule below only when you need
    field-change scope but cannot create site webhooks.

The idea is to hand-craft a body that mimics a real Jira webhook, including a
``changelog``, rather than letting the bridge read the Issue for you. The
bridge then syncs only the fields listed in that changelog.

Use the same URL, method and content type as above, but set **Custom data** to:

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

This is not strict JSON as written — it embeds Jira smart values that Jira
expands before sending. A few things worth knowing:

* Because there is a ``changelog``, this is a single-field (or few-field) sync,
  not a full sync. Comments and worklogs are not pulled in.
* ``{{issue.asJsonString}}`` expands to the whole ``fields`` object, so you
  don't have to list fields by hand.
* ``{{#changelog.changedFields}}…{{/changelog.changedFields}}`` loops over the
  changed fields. ``{{^last}},{{/last}}`` puts commas between entries but not
  after the last one — without it the JSON is invalid.
* The ``changelog`` block only makes sense for field-change triggers. For an
  issue-created rule, drop it and set ``"webhookEvent": "jira:issue_created"``.
* Because the rule reports the human who triggered it (``initiator``), a change
  made by the bridge user is ignored — normally what you want.

For developers
**************

Implementation notes; not needed to set up a rule.

* Both request shapes require the
  :class:`~sg_jira.handlers.entities_generic_handler.EntitiesGenericHandler`
  (via :class:`~sg_jira.entities_generic_syncer.EntitiesGenericSyncer`). The
  legacy ``EntityIssueHandler`` rejects automation events because they carry no
  changelog.
* Normalization happens in
  :func:`sg_jira.jira_automation_payload.normalize_automation_request`, called
  from the ``jira2sg`` branch of the web app before the event reaches a syncer.
  Payloads without the ``source`` sentinel pass through untouched, so real Jira
  webhooks are unaffected.
* Normalized events carry
  :data:`~sg_jira.constants.JIRA_EVENT_AUTOMATION_FULL_SYNC`
  (``_bridge_automation_full_sync``). The handler uses it to waive the
  changelog requirement and run a full sync. The flag is stripped from every
  inbound body and only ever set server-side, so a caller cannot forge it.
* A full sync cascades to comments and worklogs through
  ``_sync_jira_comments_to_sg`` and ``_sync_jira_worklogs_to_sg``. Each returns
  early unless ``Note`` / ``TimeLog`` appears in the configured
  ``entity_mapping``.
* Malformed automation requests raise
  :class:`~sg_jira.jira_automation_payload.JiraAutomationPayloadError`, which
  the web app maps to HTTP 400.
* Jira automation web requests cannot sign their payloads and the bridge does
  not authenticate callers, so a deployment reachable from the public internet
  should sit behind a reverse proxy enforcing a shared secret, or a network
  allowlist. This is the same exposure as the webhook endpoint.
