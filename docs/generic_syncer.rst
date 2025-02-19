Generic Syncer
##############

Description
***********

Configuration
*************

At this point, we are assuming that the Jira Bridge configuration has been correctly done following the main configuration process.

Jira Configuration
==================

As we are now supporting both way syncing, a new field has been introduced to Jira to control whether or not an Issue will be synced to Flow Production Tracking.
For each Issue Type you'd like to sync, you need to make sure that the custom field ``Sync In FPTR`` (type ``Select List (single choice)``) is enabled and contains two options: ``False`` and ``True``.

How to enable the syncer
========================

To use this generic syncer, you need to point at the right entry in the settings file.
In order to do that, you have to make sure the right URLs are used in both Flow Production Tracking and Jira.

Looking at the syncer entry in the ``settings.py`` file

.. code-block:: python

    SYNC = {
        # Add the test syncer to the list of syncers, it will be available
        # with the http://<your server>/jira2sg/entities and http://<your server>/sg2jira/entities
        # urls.
        "entities": {
            # Example of a custom syncer with an additional parameter to define
            # a log level.
            "syncer": "sg_jira.EntitiesGenericSyncer",
            "settings": {
            },
        }
    }


You need to make sure that:
    *  ``http://<your server>/sg2jira/entities`` is used in the ``Jira Sync URL`` field of your Flow Production Tracking Project
    * ``http://<your server>/jira2sg/entities`` is used in the webhook URL on the Jira side

Modifying the settings
======================

To have an easier way to configure/customize what to sync between Flow Production Tracking and Jira, everything is now done
through the ``settings.py`` file by mapping Flow Production Tracking entity type/fields with Jira Issue type/fields.

Defining entity syncing
-----------------------

.. code-block:: python

    SYNC = {
        # Add the test syncer to the list of syncers, it will be available
        # with the http://<your server>/jira2sg/entities and http://<your server>/sg2jira/entities
        # urls.
        "entities": {
            # Example of a custom syncer with an additional parameter to define
            # a log level.
            "syncer": "sg_jira.EntitiesGenericSyncer",
            "settings": {
                "entity_mapping": [
                    {
                         "sg_entity": "Task",
                         "jira_issue_type": "Task",
                         "field_mapping": [
                            {
                                 "sg_field": "content",
                                 "jira_field": "summary",
                            }
                         ]
                    }
                ]
            },
        }
    }


For each Flow Production Tracking entity you'd like to sync in Jira, you need to add a new entry to the ``entity_mapping`` list by defining the following keys:
    * ``sg_entity``: type of Flow Production Tracking entity to sync to Jira
    * ``jira_issue_type``: type of the Jira Issue associated to the FPTR entity
    * ``field_mapping``: list of FPTR/Jira fields to sync. Each list entry is a dictionary where
        * ``sg_field`` is the FPTR field code
        * ``jira_field`` is the Jira field name

Only the fields added in the ``field_mapping`` will be synced between Flow Production Tracking and Jira.


Specifying sync direction
-------------------------

It is also possible to specify a sync direction in the settings. For example, if for a specific entity or field, you only want to sync one way, you can easily specify it.
By default, the sync direction is configured to work both way.

.. code-block:: python

    SYNC = {
        # Add the test syncer to the list of syncers, it will be available
        # with the http://<your server>/jira2sg/entities and http://<your server>/sg2jira/entities
        # urls.
        "entities": {
            # Example of a custom syncer with an additional parameter to define
            # a log level.
            "syncer": "sg_jira.EntitiesGenericSyncer",
            "settings": {
                "entity_mapping": [
                    {
                         "sg_entity": "Task",
                         "jira_issue_type": "Task",
                         "sync_direction": "both_way",
                         "field_mapping": [
                            {
                                 "sg_field": "content",
                                 "jira_field": "summary",
                                 "sync_direction": "jira_to_sg",
                            }
                         ]
                    }
                ]
            },
        }
    }

The ``sync_direction`` key can take three values:
    * ``both_way``: the data will be synced both way (from FPTR to Jira and from Jira to FPTR)
    * ``sg_to_jira``: the data will be synced only from FPTR to Jira meaning that if a field value is changed in FPTR, it will be reflected in Jira. But if a value is changed in Jira, the associated field won't be updated in FPTR.
    * ``jira_to_sg``: the data will be synced only from Jira to FPTR

If the ``sync_direction`` key is not defined, the ``both_way`` direction will be used by default.

Status mapping
--------------

It is also to sync status between a Jira Issue and a Flow Production Tracking entity.
In order to do that, you can add the ``status_mapping`` key to the entity dictionary entry. Then, you only have to define
the mapping between FPTR entity status and the Jira Issue status.

.. code-block:: python

    SYNC = {
        # Add the test syncer to the list of syncers, it will be available
        # with the http://<your server>/jira2sg/entities and http://<your server>/sg2jira/entities
        # urls.
        "entities": {
            # Example of a custom syncer with an additional parameter to define
            # a log level.
            "syncer": "sg_jira.EntitiesGenericSyncer",
            "settings": {
                "entity_mapping": [
                    {
                         "sg_entity": "Task",
                         "jira_issue_type": "Task",
                         "field_mapping": [
                            {
                                 "sg_field": "content",
                                 "jira_field": "summary",
                            }
                         ],
                         "status_mapping": {
                            "sync_direction": "jira_to_sg",
                            "sg_field": "sg_status_list",
                            "mapping": {
                                "wtg": "To Do",
                                "rdy": "Open",
                                "ip": "In Progress",

                            }
                        }
                    }
                ]
            },
        }
    }


The ``status_mapping`` setting is a dictionary which takes the following keys:
    * ``sg_field`` is the FPTR status field we want to sync to Jira. As a F
PTR can have many status field but a Jira Issue has only one status, we don't need to specify the associated Jira field here.
    * ``sync_direction`` is the optional field to specify the sync direction to apply. The different values that can be used can be found in the section above.
    * ``mapping`` is a dictionary where the key is the short name of the FPTR field to sync and the key is the value of the associated Jira status

TimeLogs & Notes
----------------

TimeLog & Notes are entities with a specific behavior are they are linked to entities synced in Jira as Issues.

To enable Note syncing, you only need to add the entry in the ``entity_mapping`` dictionary but you don't need to specify the associated Jira entity nor add the ``field_mapping`` key as the mapping will be
done internally. Flow Production Tracking Note entities will be mapped to Jira Issue comments.

.. code-block:: python

    SYNC = {
        # Add the test syncer to the list of syncers, it will be available
        # with the http://<your server>/jira2sg/entities and http://<your server>/sg2jira/entities
        # urls.
        "entities": {
            # Example of a custom syncer with an additional parameter to define
            # a log level.
            "syncer": "sg_jira.EntitiesGenericSyncer",
            "settings": {
                "entity_mapping": [
                    {
                         "sg_entity": "Task",
                         "jira_issue_type": "Task",
                         "field_mapping": [
                            {
                                 "sg_field": "content",
                                 "jira_field": "summary",
                            }
                         ]
                    },
                    {
                        "sg_entity": "Note",
                        "sync_deletion_direction": "jira_to_sg",
                    }
                ]
            },
        }
    }

Regarding the TimeLog entity, you have to specify the ``field_mapping`` but the Jira entity mapping will be done internally as well.
Flow Production Tracking TimeLog entities will be mapped to Jira Issue worklogs.

.. code-block:: python

    SYNC = {
        # Add the test syncer to the list of syncers, it will be available
        # with the http://<your server>/jira2sg/entities and http://<your server>/sg2jira/entities
        # urls.
        "entities": {
            # Example of a custom syncer with an additional parameter to define
            # a log level.
            "syncer": "sg_jira.EntitiesGenericSyncer",
            "settings": {
                "entity_mapping": [
                    {
                         "sg_entity": "Task",
                         "jira_issue_type": "Task",
                         "field_mapping": [
                            {
                                 "sg_field": "content",
                                 "jira_field": "summary",
                            }
                         ]
                    },
                    {
                        "sg_entity": "TimeLog",
                        "sync_direction": "sg_to_jira",
                        "field_mapping": [
                            {
                                "sg_field": "date",
                                "jira_field": "started",
                            },
                            {
                                "sg_field": "duration",
                                "jira_field": "timeSpentSeconds",
                            },
                            {
                                "sg_field": "description",
                                "jira_field": "comment",
                            },
                        ]
                    }
                ]
            },
        }
    }

Both ``Note`` and ``TimeLog`` entities support the ``sync_direction`` key.
As they are also supporting deletion, a new ``sync_deletion_direction`` key can be defined for both of these entities and allows you
to specify how you want to handle deletion. By default, the value of this key is ``None`` meaning that the deletion is disabled both way.
If you want to enable it, you can specify the way by using one of the value used by the ``sync_direction`` key.

Hook
****

Use Case: Epic linking syncing
******************************

Here, we want to mimic the Epic/Task Jira relationship in Flow Production Tracking and have everything synchronized.

Flow Production Tracking configuration
======================================

First, make sure you have a CustomProjectEntity representing an Epic enabled in Flow Production Tracking.

.. image:: _static/epic_syncing_enable_entity.png

Ensure that the mandatory FPTR fields are created for this entity type.

============= =========== ======================================= ============================
Field Name    Field Type  Description                             Field Code (auto-generated)
============= =========== ======================================= ============================
Jira Sync URL File/Link   URL of the associated Jira Bridge Issue  ``sg_jira_sync_url``
Jira Key      Text        Synced Issue Key value in Jira           ``sg_jira_key``
Sync In Jira  Checkbox    Enable/Disable syncing for this Entity   ``sg_sync_in_jira``
============= =========== ======================================= ============================

On the ``Task`` entity, create an ``entity`` field to be able to link an Epic entity to a Task entity in Flow Production Tracking.

.. image:: _static/epic_syncing_epic_field.png

Jira configuration
==================

Enable the Issue Type ``Epic`` in Jira and check for the hierarchy setting that the ``Task`` Issue type accepts the ``Epic`` Issue type as parent.
Also, make sure that the new ``Sync in FPTR`` field option exists for the ``Epic`` Issue type.

Setting configuration
=====================

Once everything has been correctly configured in both Jira and Flow Production Tracking, we need to make sure that the mapping is done in the ``settings.py`` file.

.. code-block:: python

    SYNC = {
        # Add the test syncer to the list of syncers, it will be available
        # with the http://<your server>/jira2sg/entities and http://<your server>/sg2jira/entities
        # urls.
        "entities": {
            # Example of a custom syncer with an additional parameter to define
            # a log level.
            "syncer": "sg_jira.EntitiesGenericSyncer",
            "settings": {
                "entity_mapping": [
                    {
                         "sg_entity": "Task",
                         "jira_issue_type": "Task",
                         "field_mapping": [
                            {
                                 "sg_field": "content",
                                 "jira_field": "summary",
                            },
                            {
                                "sg_field": "sg_epic",
                                "jira_field": "parent",
                            },
                         ]
                    },
                    {
                        "sg_entity": "CustomEntity04",
                        "jira_issue_type": "Epic",
                        "field_mapping": [
                            {
                                "sg_field": "code",
                                "jira_field": "summary",
                            },
                        ],
                    }
                ]
            },
        }
    }


You need to make sure that:
    * the FPTR ``Task`` entity has been added to the entity mapping, is correctly mapped to the Task Issue type, and its ``parent`` field has been added to the field mapping
    * the FPTR ``Epic`` entity (CustomEntity04) has been added to the entity mapping and is correctly mapped to the Epic Issue type


FPTR Event Daemon Configuration
===============================

In order to have the sync working from FPTR to Jira, you need to make sure to add the corresponding event to the ``sg_jira_event_trigger`` plugin.

.. code-block:: python

    def registerCallbacks(reg):
        """
        Register all necessary or appropriate callbacks for this plugin.

        Flow Production Tracking credentials are retrieved from the `SGDAEMON_SGJIRA_NAME` and `SGDAEMON_SGJIRA_KEY`
        environment variables.

        :param reg: A Flow Production Tracking Event Daemon Registrar instance.
        """
        # Narrow down the list of events we pass to the bridge
        event_filter = {
            "Shotgun_Note_Change": ["*"],
            "Shotgun_Task_Change": ["*"],
            "Shotgun_Ticket_Change": ["*"],
            "Shotgun_Project_Change": ["*"],
            "Shotgun_CustomEntity04_Change": ["*"],  # Needed to sync the Task/Epic linking
            # These events require a reset of the bridge to ensure our cached schema
            # is up to date.
            "Shotgun_DisplayColumn_New": ["*"],
            "Shotgun_DisplayColumn_Change": ["*"],
            "Shotgun_DisplayColumn_Retirement": ["*"],
            "Shotgun_Status_New": ["*"],
            "Shotgun_Status_Change": ["*"],
            "Shotgun_Status_Retirement": ["*"],
        }