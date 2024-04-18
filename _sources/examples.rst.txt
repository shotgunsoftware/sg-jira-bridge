Examples
########

Flow Production Tracking Jira Bridge comes with several examples that can be found in
the `examples <https://github.com/shotgunsoftware/sg-jira-bridge/tree/master/examples>`_ folder.

These examples can be loaded if the `examples` directory is added to the PYTHONPATH in the
`settings.py <https://github.com/shotgunsoftware/sg-jira-bridge/blob/master/settings.py#L95>`_ file.

To set up your custom syncer, you need to correctly reference it in these two places:
- Add its name in the ``Jira Sync URL`` field of your Flow Production Tracking Project
- Add its name in the Webhook URL on the Jira side

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
It is working both ways: from Flow Production Tracking to Jira and vice-versa.
It also handles TimeLog/Worklog deletions.

TimeLog Creation
----------------

When a TimeLog is created in Flow Production Tracking, an associated Worklog will
be created in Jira.

.. note::
    Only Timelogs associated to a synced Task will be pushed to Jira. If a TimeLog is created
    in Flow Production Tracking but is linked to a Task that doesn't have the ``Sync In Jira`` field checked,
    a Jira Worklog will _not_ be created.

.. warning::
    Due to a Jira API limitation, it is not currently possible to set the Worklog assignee.
    Flow Production Tracking TimeLog assignees are stored as JSON data and can be trackable in a
    custom field on the Jira Issue.
    Please, look at the :ref:`Jira Workaround`
    section if you want to have more information.

When a Worklog is created in Jira, an associated Timelog will be created in Flow Production Tracking.
The user who created the Worklog in Jira will be used as the Timelog assignee as soon as an associated
user can be found in Flow Production Tracking.

TimeLog Update
--------------

When a TimeLog has an associated Jira Worklog and  is updated in Flow Production Tracking,
the Timelog will be updated too.

.. warning::
    Due to a Jira API limitation, it is not currently possible to set the Worklog assignee.
    So when a Timelog assignee is updated in Flow Production Tracking, the Jira Worklog
    assignee will remain unchanged. Since we are using a custom field on the Jira Issue to track
    TimeLog assignees, this Timelog field will be updated accordingly.

When a Worklog in Jira is updated and has an associated Flow Production Tracking Timelog,
this Timelog field will be updated as well.

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


When ``sync_sg_timelog_deletion`` is set to True and a Worklog is deleted in Jira, its associated Flow Production
Tracking Timelog will also be deleted. If it is set to False, the Flow Production Tracking Timelog will remain unchanged.

Likewise, when``sync_jira_worklog_deletion`` is set to True and a Timelog is deleted in Flow Production Tracking, its associated Jira Worklog will also be deleted. If it is set to False, the Jira worklog will remain unchanged.

Refresh Synced Task
-------------------

The ``Sync In Jira`` field on the Flow Production Tracking Task entity allows the user to control
whether a Task is synced to a Jira Issue. Re-enabling this field on a Flow Production Tracking Task will launch a full synchronization
of the Task and its TimeLogs.

* If Timelogs have been created in Flow Production Tracking when the Task sync was inactive, they will be created in Jira as new Worklogs.
* If a Task had Timelogs already created in Jira, they will be updated accordingly.
* If Timelogs have been deleted when the Task sync was inactive, they will not be deleted in Jira.
* If Worklogs have been created in Flow Production Tracking when the Task sync was inactive, they will be created in Flow Production Tracking as new Timelogs.

.. note::
    Task synchronizations start by examining the Flow Production Tracking Timelogs. Once they are created and/or updated in Jira, it will progress to pushing the remaining Jira Worklogs to Flow Production Tracking. That said, if someone modified a Worklog in Jira when the Task sync was inactive, and this is Worklog already has an associated Flow Production Tracking Timelog, the changes will not be reflected in Flow Production Tracking.

.. note::
    Timelog and Worklog deletions are not influenced when doing a full Task synchronizations.


Configuration
=============

Setting up Flow Production Tracking
-----------------------------------

The following field must be created in Flow Production Tracking for each of the
TimeLog entity types:

===========  =========  ================  ====================================  ======================
Entity Type  Data Type  Display Name      Description                           Field Name (auto-generated)
===========  =========  ================  ====================================  ======================
TimeLog      Text       Jira Key          Synced Issue Key value in Jira        ``sg_jira_key``
===========  =========  ================  ====================================  ======================

.. note::
    Enable the "*Ensure unique  value per project*" setting  in the Configure Field... dialog. To ensure this setting is enabled on the field, right-click the field header in list view, select ``Configure field...``, check the "*Ensure unique  value per project*" option and update.

Setting up Jira
---------------

Due to Jira API limitations, it is not possible to set the Jira Worklog assignee.
To keep a track of the Flow Production Tracking Timelog assignees, create a custom field
on the Jira Issue entity.

+------------------+-----------+--------------------------------------------------------------+
| Field Name       | Type      | Description                                                  |
+==================+===========+==============================================================+
| Shotgun TimeLogs | Paragraph | Stores the Flow Production Tracking Timelog assignees        |
+------------------+-----------+--------------------------------------------------------------+

.. note::
    Since this custom field stores JSON data, using the typical ``Text`` field type presents
    character length limitation issues. The ``Paragraph`` field type is required instead, but it's important to note that it is editable and doesn't  have a ``read-only`` property.

You also need to make sure that the following events are enabled in the :ref:`Jira Webhook` settings:

* **Worklog:** created
* **Worklog:** updated
* **Worklog:** deleted

.. _Jira Workaround:

Jira API Limitations & Workarounds
==================================

Due to some Jira API limitations, it is not currently possible to set or update the Jira Worklog assignees.
To track Flow Production Tracking Timelog assignees, we have implemented a generic solution
using a custom field on the Issue entity.

If you would like to implement your own solution, it is possible to modify the content of the following methods in
the Timelog syncer:

* ``_add_sg_user_to_jira_worklog()``
* ``_remove_sg_user_from_jira_worklog()``
* ``_get_sg_user_from_jira_worklog()``
