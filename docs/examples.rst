Examples
########

Flow Production Tracking Jira Bridge comes with several examples than can be found in
the `examples <https://github.com/shotgunsoftware/sg-jira-bridge/tree/master/examples>`_ folder.

These examples can be loaded if the `examples` directory is added to the PYTHONPATH in the
`settings.py <https://github.com/shotgunsoftware/sg-jira-bridge/blob/master/settings.py#L95>`_ file.

To properly use your custom syncer, you need to make sure you're correctly referencing it.
This is done by using its name in the ``Jira Sync URL`` field of your Flow Production Tracking Project
as well as in the Webhook URL on the Jira side.

For example, this is how a syncer is defined in the `settings.py` file and how the urls should look like

.. code-block:: python

    SYNC = {
        # Add the test syncer to the list of syncers, it will be available
        # with the http://<your server>/jira2sg/test and http://<your server>/sg2jira/test
        # urls.
        "test": {
            # Example of a custom syncer with an additional parameter to define
            # a log level.
            "syncer": "example_sync.ExampleSync",
            "settings": {
                "log_level": logging.DEBUG
            },
        }
    }


TimeLog Syncer
**************

Description
===========

The TimeLog syncer allows the synchronization of Flow Production Tracking TimeLogs with Jira Worklogs.
It is working both way: from Flow Production Tracking to Jira and vice-versa.
It also handles TimeLog/Worklog deletion.

TimeLog Creation
----------------

When a TimeLog is created in Flow Production Tracking, an associated worklog will
be created in Jira.

.. note::
    Only the Timelogs associated to a synced Task will be pushed to Jira. If a TimeLog is created
    in Flow Production Tracking but is linked to a Task which don't have the ``Sync In Jira`` field checked,
    no Jira Worklog will be created.

.. warning::
    Due to Jira API limitation, it is not possible right now to set the Worklog assignee.
    In order to keep a track of the PTR TimeLog assignee, they are stored as JSON data in a
    custom field on the Jira Issue.
    Please, look at the :ref:`Jira Workaround`
    section if you want to have more information.

When a Worklog is created in Jira, an associated Timelog will be created in Flow Production Tracking.
The user who created the worklog in Jira will be used as the Timelog assignee as soon as an associated
user can be found in Flow Production Tracking.

TimeLog Update
--------------

When a TimeLog is updated in Flow Production Tracking and if it has an associated Jira Worklog,
this one will be updated too.

.. warning::
    Due to Jira API limitation, it is not possible right now to update a Worklog assignee.
    So when a Timelog assignee is updated in Flow Production Tracking, the Jira Worklog
    assignee won't be updated. As we are using a custom field on the Jira Issue to keep a track
    on the TimeLog assignees, this field will be updated accordingly.

When a Worklog in Jira is updated and has an associated Flow Production Tracking Timelog,
this one will be updated as well.

TimeLog Deletion
----------------

The Timelog syncer comes with two settings defined in the `settings.py <https://github.com/shotgunsoftware/sg-jira-bridge/blob/master/settings.py>`__
file to manage the deletion of Timelog/Worklog in Flow Production Tracking and Jira.

.. code-block:: python

    "timelog": {
        # The syncer class to use
        "syncer": "timelog_worklog.TimelogWorklogSyncer",
        # And its specific settings which are passed to its __init__ method
        "settings": {
            "issue_type": "Task",
            # If True, when a worklog is deleted in Jira it will also be deleted in Flow Production Tracking
            "sync_sg_timelog_deletion": True,
            # If True, when a timelog is deleted in Flow Production Tracking, it will also be deleted in Jira
            "sync_jira_worklog_deletion": True,
        },
    }


If ``sync_sg_timelog_deletion`` is set to True, when a Worklog is deleted in Jira and has an associated Flow Production
Tracking Timelog, this one will also be deleted. If it is set to False, the Flow Production Tracking Timelog won't
be deleted.

If ``sync_jira_worklog_deletion`` is set to True, when a Timelog is deleted in Flow Production Tracking and has an
associated Jira Worklog, this one will also be deleted. If it is set to False, the Jira worklog won't
be deleted.

Refresh Synced Task
-------------------

The field ``Sync In Jira`` existing on the Flow Production Tracking Task entity allows the user to control
whether a Task is synced to a Jira Issue. Re-enabling this field on a PTR Task will launch a full synchronization
of the Task and its TimeLogs.

* If Timelogs have been created in Flow Production Tracking when the Task synced was disabled, they will be created in Jira as new Worklogs.
* If the Task had Timelogs already created in Jira, they will be updated accordingly.
* If Timelogs have been deleted when the Task synced was disabled, they won't be deleted in Jira.
* If Worklogs have been created in Flow Production Tracking when the Task synced was disabled, they will be created in Flow Production Tracking as new Timelogs.

.. note::
    When doing a full Task synchronization, it will start by looking at the Flow Production Tracking Timelogs
    and once they are created/updated in Jira, it will look at the remaining Jira Worklogs and push them to
    Flow Production Tracking. That means if someone modified worklog in Jira when the Task synced was disabled,
    and this is worklog already has an associated PTR Timelog, the changes won't be reflected in Flow Production
    Tracking.

.. note::
    Timelog and Worklog deletions are not taken into account when doing a full Task synchronization.


Configuration
=============

Setting up Flow Production Tracking
-----------------------------------

The following field must be created in Flow Production Tracking for each of the
TimeLog entity type:

===========  =========  ================  ====================================  ======================
Entity Type  Data Type  Display Name      Description                           Field Name (auto-generated)
===========  =========  ================  ====================================  ======================
TimeLog      Text       Jira Key          Synced Issue Key value in Jira        ``sg_jira_key``
===========  =========  ================  ====================================  ======================

.. note::
    Make sure the field is configured with the "*Ensure unique
    value per project*" setting **checked**. This setting can be found by
    showing the relevant field in an entity spreadsheet view and then
    right clicking the header for that column. Select the ``Configure field...``
    menu option.

Setting up Jira
---------------

Because of the Jira API limitations, it is not possible to set the Jira Worklog assignee.
To keep a track of the Flow Production Tracking Timelog assignees, we are using a custom field
on the Jira Issue entity that need to be created.

+------------------+-----------+--------------------------------------------------------------+
| Field Name       | Type      | Description                                                  |
+==================+===========+==============================================================+
| Shotgun TimeLogs | TextField | Stores the Flow Production Tracking Timelog assignees        |
+------------------+-----------+--------------------------------------------------------------+

.. note::
    Because this custom field will store JSON data, we can't use a ``Text`` field as it has
    a character length limitation. This is why we are using a ``TextField`` field.
    Unfortunately, this type of field doesn't have a ``read-only`` property.

.. _Jira Workaround:
Jira API Limitations & Workaround
=================================

Because of some Jira API limitations, it is not possible right now to set or update the Jira Worklog assignees.
In order to keep a track of the Flow Production Tracking Timelog assignees, we have implemented a generic solution
using a custom field on the Issue entity.

If you want to implement your own solution, it is possible to modify the content of the following methods in
the Timelog syncer:

* ``_add_sg_user_to_jira_worklog()``
* ``_remove_sg_user_from_jira_worklog()``
* ``_get_sg_user_from_jira_worklog()``
