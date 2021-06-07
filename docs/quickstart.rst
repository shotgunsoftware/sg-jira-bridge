.. _quickstart:


Quick Start
###########
The instructions below will help you get up and running quickly.

Requirements
************
- Python 2.7
- A ShotGrid site
- A Jira site


Getting the Code
****************
The quickest way to get the code required is by cloning the Github repos

- SG Jira Bridge: https://github.com/shotgunsoftware/sg-jira-bridge
- shotgunEvents: https://github.com/shotgunsoftware/shotgunEvents

.. code-block:: bash

    $ cd /path/to/put/this
    $ git clone git@github.com:shotgunsoftware/sg-jira-bridge.git
    $ git clone git@github.com:shotgunsoftware/shotgunEvents.git


A note about Jira servers hosted by Atlassian
*********************************************

In April 2019, Atlassian put a new set of rules around accessing user data
due to the the European GDPR regulation. Since then, email addresses of Jira
users are no longer accessible.

As the ShotGrid Jira bridge relies on this information to pair ShotGrid users
with Jira users, some extra steps will be required to configure the Jira
bridge. This quickstart page will alert you when these extra steps are needed.


Setting up ShotGrid
*******************
Required Fields
===============
The following fields must be created in ShotGrid for each of the
following entity types:

===========   ======================   =========   ==========================   ==========================
Entity Type   Field Name               Data Type   Display Name (recommended)   Description
===========   ======================   =========   ==========================   ==========================
Project       ``sg_jira_sync_url``     File/Link   Jira Sync URL                URL of SG Jira Bridge (see below)
Project       ``sg_jira_key``          Text        Jira Key*                    Synced Project Key value in Jira
Task          ``sg_jira_key``          Text        Jira Key*                    Synced Issue Key value in Jira
Task          ``sg_sync_in_jira``      Checkbox    Sync In Jira                 Enable/Disable syncing for this Task
Task          ``sg_jira_url``          File/Link   Jira URL                     Link to synced Issue in Jira
Note          ``sg_jira_key``          Text        Jira Key*                    Synced Issue Key/Comment ID in Jira
HumanUser     ``sg_jira_account_id``   Text        Jira Account Id              Synced Account Id in Jira.
===========   ======================   =========   ==========================   ==========================

.. note::
    - All ``sg_jira_key`` fields must be configured with the "*Ensure unique
      value per project*" setting **checked**. This setting can be found by
      showing the relevant field in an entity spreadsheet view and then
      right clicking the header for that column. Select the ``Configure field...``
      menu option.
    - The ``HumanUser.sg_jira_account_id`` field is only necessary if your
      Jira server is hosted by Atlassian.


Configure your ShotGrid Project
===============================
Configure your ShotGrid Project entity with your Jira Sync Settings:

+--------------+------------------------------------------+-----------------------------------------+
| Field        | Value                                    | Description                             |
+==============+==========================================+=========================================+
| Jira Sync URL| ``http://localhost:9090/sg2jira/default``| The address where you'll run the SG     |
|              |                                          | Jira Bridge webserver                   |
+--------------+------------------------------------------+-----------------------------------------+
| Jira Key     | <JIRA PROJECT KEY>                       | The Project Key in Jira for the Project |
|              |                                          | you're syncing (eg ``TEST``).           |
+--------------+------------------------------------------+-----------------------------------------+



Setting up Jira
***************
Required Fields
===============
The following fields must be created in Jira and made available in Boards:

+--------------+------+-----------------------------------------------------------------------+
| Field Name   | Type | Description                                                           |
+==============+======+=======================================================================+
| Shotgun Type | Text | Stores the associated ShotGrid Entity type                            |
+--------------+------+-----------------------------------------------------------------------+
| Shotgun ID   | Text | Stores the associated ShotGrid Entity ID                              |
+--------------+------+-----------------------------------------------------------------------+
| Shotgun URL  | Text | Stores a link to the detail page for the associated entity in ShotGrid|
+--------------+------+-----------------------------------------------------------------------+

Jira Webhook
============

- Navigate to the Jira system settings (*Settings > System > WebHooks*)
- Click "Create Webhook"
- Add the values for the following:

+--------------+-----------------------------------------------------------------------------------------+
| Field        | Example                                                                                 |
+==============+=========================================================================================+
| Name         | "SG Jira Bridge Test"                                                                   |
+--------------+-----------------------------------------------------------------------------------------+
| URL          | | ``https://<url_for_sg_jira_bridge>/jira2sg/default/issue/${issue.key}``               |
|              | | The ``<url_for_sg_jira_bridge>`` is the host name or IP address of the computer you   |
|              | | will be launching ``webapp.py`` or ``service.py`` from.                               |
+--------------+-----------------------------------------------------------------------------------------+
| Description  | "Webhook that syncs Jira data with ShotGrid using the SG Jira Bridge"                   |
+--------------+-----------------------------------------------------------------------------------------+
| JQL          | ``project = "Your Project Name"``                                                       |
+--------------+-----------------------------------------------------------------------------------------+
| Events       | - (`required`) **[x]** Issue: created, updated, deleted                                 |
|              | - (`required`) **[x]** Comment: created, updated, deleted                               |
+--------------+-----------------------------------------------------------------------------------------+
| Exclude Body | (`required`) **[ ] un-checked**                                                         |
+--------------+-----------------------------------------------------------------------------------------+

.. note::
    If you are setting up a local development environment and need Jira to have access to localhost
    in order for the Jira webhook to successfully delivery its payload to the bridge, be sure to
    follow the instructions in the ``Testing on a Machine Not Accessible to Jira`` section of the
    debugging guide.


Setting Up Your Config and Env
******************************

There are two different pieces to setting up the ShotGrid Jira Bridge. There's the bridge itself
(``sg-jira-bridge``), which handles all of the syncing of data between ShotGrid and Jira. Then
there's the ShotGrid Event Daemon (``shotgunEvents``), which handles dispatching supported ShotGrid
events to the bridge.

Since they are installed in different locations and each setup has different python module
requirements, the instructions below describe how to setup an environment for each of them
separately.

SG Jira Bridge
==============
Installing Required Modules
---------------------------
We recommend `setting up a virtual environment <https://docs.python-guide.org/dev/virtualenvs/>`_.
Ensure you have `virtualenv <https://pypi.org/project/virtualenv/>`_ installed in your global Python installation.
A ``requirements.txt`` file is provided to install all required packages.

.. code-block:: bash

    # create a virtualenv
    $ virtualenv venv

    # Activate the virtualenv
    # On MacOS/Linux:
    $ source venv/bin/activate
    # On Windows (using PowerShell)
    $ venv/Scripts/activate

    # Install required packages
    pip install -r /path/to/sg-jira-bridge/requirements.txt

.. note::
    If you are upgrading from a previous version of the bridge, we recommend you upgrade the dependencies
    as we've had to fork the ``jira`` Python module to add a missing feature:

    .. code-block::

        pip install --upgrade -r /path/to/sg-jira-bridge/requirements.txt


Settings
--------
Settings are defined in the ``settings.py`` file in the root of the repo. For the quickstart,
the default settings are fine as-is.

Authentication
--------------
Credentials are retrieved from environment variables. You may set these in your
environment or use `python-dotenv <https://pypi.org/project/python-dotenv>`_
and define these in a ``.env`` file.

::

    # ShotGrid credentials
    SGJIRA_SG_SITE='https://mysite.shotgrid.autodesk.com'
    SGJIRA_SG_SCRIPT_NAME='sg-jira-bridge'
    SGJIRA_SG_SCRIPT_KEY='01234567@abcdef0123456789'  # replace with your api key

    # Jira credentials
    SGJIRA_JIRA_SITE='https://mystudio.atlassian.net'
    SGJIRA_JIRA_USER='richard.hendricks@piedpiper.com'
    SGJIRA_JIRA_USER_SECRET='youkn0wwh@tapa$5word1smAKeitag0odone3'  # replace with your user's password or API key

.. note::

    **Jira Cloud** requires the use of an API token and will not work with
    a user password. See https://confluence.atlassian.com/x/Vo71Nw for information
    on how to generate a token.

    **Jira Server** will still work with a user password and does not support
    API tokens.

    For more information, see: https://developer.atlassian.com/cloud/jira/platform/jira-rest-api-basic-authentication/

.. note::

    Since Jira does not have a concept of a "script" user, ``SGJIRA_JIRA_USER``
    will need to be the designated user account, with appropriate
    permissions, that will control the sync updates. Note that the user should
    not be your personal user account, as the bridge will ignore and not sync
    to ShotGrid any events triggered in Jira by that user. This ensures that
    the bridge will not end up in a "ping pong" state, where it bounces the
    same event back-and-forth between Jira and ShotGrid. As such, you will need
    to create a dedicated user account in Jira for use with the bridge.


shotgunEvents
=============
Details for configuring the ShotGrid Event Daemon are available on the
`shotgunEvents wiki <https://github.com/shotgunsoftware/shotgunEvents/wiki>`_

Installing Required Modules
---------------------------
We recommend `setting up a virtual environment <https://docs.python-guide.org/dev/virtualenvs/>`_.
Ensure you have `virtualenv <https://pypi.org/project/virtualenv/>`_ installed in your global Python installation.

.. code-block:: bash

    # create a virtualenv
    $ virtualenv venv

    # Activate the virtualenv
    # On MacOS/Linux:
    $ source venv/bin/activate
    # On Windows (using PowerShell)
    $ venv/Scripts/activate

    # Install required packages for the trigger.
    # Note: This requirements.txt is in the "sg-jira-bridge/triggers"
    #       subdirectory, NOT in the root of the project.
    pip install -r /path/to/sg-jira-bridge/triggers/requirements.txt

Enable the SG Jira Trigger
--------------------------
Add the path to the SG Jira Bridge ``sg_jira_event_trigger.py`` file to the
shotgunEvents conf file::

    ...
    [plugins]
    # Plugin related settings

    # A comma delimited list of paths where the framework should look for plugins to
    # load.
    paths: /path/to/sg_jira_bridge/triggers, /path/to/any/other/shotgunEvents/plugins
    ...

Authentication
--------------
The trigger uses the following environment variables to retrieve ShotGrid
credentials::

    # sg_jira_event_trigger.py credentials
    SGDAEMON_SGJIRA_NAME='sg_jira_event_trigger'
    SGDAEMON_SGJIRA_KEY='01234567@abcdef0123456789'  # replace with your api key

.. note::

    The trigger uses it's own authentication to ShotGrid, independent of the
    auth used in the SG Jira Bridge Server and the main shotgunEvents settings.
    We highly recommend you add an additional Script User in ShotGrid solely
    for this trigger.

.. note::
    If you are using sg-jira-bridge v0.2.2 or later, these environment variables can also be defined in the ``.env``
    file from the SG Jira Bridge section


Define a Mapping Between Jira and ShotGrid Status Names
-------------------------------------------------------
The bridge needs to know how to map a status in ShotGrid to a status in Jira and vice versa. Your status names likely
differ from the default ones. Make sure the values in
`TaskIssueHandler._sg_jira_status_mapping <https://github.com/shotgunsoftware/sg-jira-bridge/blob/725f63c19b45529f2507c530c7923cb4d55459e1/sg_jira/handlers/task_issue_handler.py#L47/>`_
match the names used in your workflow::

    return {
        "wtg": "Backlog",
        "rdy": "Selected For Development",
        "ip": "In Progress",
    }

Starting Everything Up
**********************

Match ShotGrid users with Jira users (for Jira servers hosted by Atlassian only)
================================================================================

.. code-block:: bash

    $ python update_shotgun_users.py --settings <path to your settings.py> --project <id of your project>

.. note::
    For every user found in ShotGrid, the script will search for a Jira user with
    the same email address. If you have multiple users in ShotGrid with
    the same email address, only the first one, i.e. the one with the lowest id,
    will be associated with a Jira account.

    If you wish to change the ShotGrid user associated with a Jira account, e.g. the
    script associated the first ShotGrid user with an account when you actually wanted
    the second one, you can take the account id from the ``HumanUser.sg_jira_account_id``
    field from one user and copy it to another user and then clear the original user's
    account id.

    If new users are added to Jira and ShotGrid, run this script again and the new user
    accounts will be paired. Existing pairings will be left as they were.

.. note::
    Due to Jira API restrictions, we can only search for email addresses of users
    that can be assigned on issues for a given Jira project. If all
    your Jira users can access any Jira project, the value for the ``--project``
    argument can be any project id. If you have restrictions, you will need to
    run this script once per project so that all your Jira users can be discovered
    and paired with a ShotGrid user.

Start SG Jira Bridge
====================
.. code-block:: bash

    $ python webapp.py --settings <path to your settings.py> --port 9090


Start shotgunEvents
===================

.. code-block:: bash

    $ ./shotgunEventDaemon.py foreground

.. note::

    This starts the event daemon in foreground mode, logging everything to the
    terminal which is helpful for testing. When running in production, you'll
    start it with ``./shotgunEventDaemon.py start``

Testing It Out
**************
Once everything is running you're ready to test it!

- Create an Asset in ShotGrid with a TaskTemplate appied.
- Toggle the **Sync In Jira** checkbox ``on`` for one of the Tasks.
- Navigate to your Jira site to see the Issue created for that Task.
- Change the status in Jira to see the status change in ShotGrid.

If things don't seem to be working, check the output from SG Jira Bridge and
shotgunEvents in your terminal window for log messages.

.. note::
    For any synced entity, ShotGrid stores the associated Jira key in the
    ``sg_jira_key`` field which will update automatically when you initially
    sync the Task. Jira stores the associated ShotGrid Entity type and ID in
    the **Shotgun Type** and **Shotgun ID** fields as well as a link to the
    entity in Shotgun in the **Shotgun URL** field. This is a good indicator
    that things are working correctly.
