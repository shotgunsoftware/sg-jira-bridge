.. _quickstart:


Quick Start
###########
The instructions below will help you get up and running quickly.

Requirements
************
- Python 2.7
- A Shotgun site
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



Setting up Shotgun
******************
Required Fields
===============
The following fields must be created in Shotgun for each of the
following entity types:

===========   ====================   =========   ==========================
Entity Type   Field Name             Data Type   Display Name (recommended)
===========   ====================   =========   ==========================
Project       ``sg_jira_sync_url``   File/Link   Jira Sync URL
Project       ``sg_jira_key``        Text        Jira Key
Task          ``sg_jira_key``        Text        Jira Key
Task          ``sg_sync_in_jira``    Checkbox    Sync In Jira
Note          ``sg_jira_key``        Text        Jira Key
===========   ====================   =========   ==========================

Configure your Shotgun Project
==============================
Configure your Shotgun Project entity with your Jira Sync Settings:

+--------------+------------------------------------------+-----------------------------------------+
| Field        | Value                                    | Description                             |
+==============+==========================================+=========================================+
| Jira Sync URL| ``http://localhost:9090/sg2jira/default``| The address where you'll run the SG     |
|              |                                          | Jira Bridge webserver                   |
+--------------+------------------------------------------+-----------------------------------------+
| Jira Key     | <JIRA PROJECT KEY>                       | The Project Key in Jira for the Project |
|              |                                          | you're syncing (eg ``TEST``)            |
+--------------+------------------------------------------+-----------------------------------------+



Setting up JIRA
***************
Required Fields
===============
The following fields must be created in Jira and made available in Boards:

+--------------+------+-----------------------------------------------------------------------+
| Field Name   | Type | Description                                                           |
+==============+======+=======================================================================+
| Shotgun Type | Text | Stores the associated Shotgun Entity type                             |
+--------------+------+-----------------------------------------------------------------------+
| Shotgun ID   | Text | Stores the associated Shotgun Entity ID                               |
+--------------+------+-----------------------------------------------------------------------+
| Shotgun URL  | Text | Stores a link to the detail page for the associated entity in Shotgun |
+--------------+------+-----------------------------------------------------------------------+

Jira Webhook
============

- Navigate to the Jira system settings (*Settings > System > WebHooks*)
- Click "Create Webhook"
- Add the values for the following:

+--------------+-------------------------------------------------------------------------+
| Field        | Example                                                                 |
+==============+=========================================================================+
| Name         | "SG Jira Bridge Test"                                                   |
+--------------+-------------------------------------------------------------------------+
| URL          | ``https://<url_for_sg_jira_bridge>/jira2sg/default/issue/${issue.key}`` |
+--------------+-------------------------------------------------------------------------+
| Description  | "Webhook that syncs Jira data with Shotgun using the SG Jira Bridge"    |
+--------------+-------------------------------------------------------------------------+
| JQL          | ``project = "Your Project Name"``                                       |
+--------------+-------------------------------------------------------------------------+
| Events       | - (`required`) **[x]** Issue: created, updated, deleted                 |
|              | - (`required`) **[x]** Comment: created, updated, deleted               |
+--------------+-------------------------------------------------------------------------+
| Exclude Body | (`required`) **[ ] un-checked**                                         |
+--------------+-------------------------------------------------------------------------+


Setting Up Your Config and Env
******************************
SG Jira Bridge
==============
Installing Required Modules
---------------------------
We recommend `setting up a virtual environment <https://docs.python-guide.org/dev/virtualenvs/>`_.
Ensure you have `virtualenv <https://pypi.org/project/virtualenv/>`_ installed in your global Python installation.
A ``requirements.txt`` file is provided to install all required packages.

.. note::

    If you use ``pipenv``, see :ref:`using-pipenv`.

.. code-block:: bash

    # create a virtualenv
    $ virtualenv venv

    # Activate the virtualenv
    # On MacOS/Linux:
    $ source venv/bin/activate
    # On Windows (using PowerShell)
    $ venv/Scripts/activate

    # Install required packages
    pip install -r requirements.txt


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

    # Shotgun credentials
    SGJIRA_SG_SITE='https://mysite.shotgunstudio.com'
    SGJIRA_SG_SCRIPT_NAME='sg-jira-bridge'
    SGJIRA_SG_SCRIPT_KEY='01234567@abcdef0123456789'  # replace with your api key

    # Jira credentials
    SGJIRA_JIRA_SITE='https://mystudio.atlassian.net'
    SGJIRA_JIRA_USER='richard.hendricks@piedpiper.com'
    SGJIRA_JIRA_USER_SECRET='youkn0wwh@tapa$5word1smAKeitag0odone3'  # replace with your user's password

.. note::

    Since Jira does not have a concept of a "script" user, ``SGJIRA_JIRA_USER``
    will need to be the designated user account, with appropriate
    permissions, that will control the sync updates.


shotgunEvents
=============
Details for configuring the Shotgun Event Daemon are available on the
`shotgunEvents wiki <https://github.com/shotgunsoftware/shotgunEvents/wiki>`_

Installing Required Modules
---------------------------
We recommend `setting up a virtual environment <https://docs.python-guide.org/dev/virtualenvs/>`_.
Ensure you have `virtualenv <https://pypi.org/project/virtualenv/>`_ installed in your global Python installation.

.. note::

    If you use ``pipenv``, see :ref:`using-pipenv`.

.. code-block:: bash

    # create a virtualenv
    $ virtualenv venv

    # Activate the virtualenv
    # On MacOS/Linux:
    $ source venv/bin/activate
    # On Windows (using PowerShell)
    $ venv/Scripts/activate

    # Install required packages
    pip install requests https://github.com/shotgunsoftware/python-api/archive/v3.0.38.zip

Enable the SG Jira Trigger
--------------------------
Add the path to the SG Jira Bridge ``sg_jira_event_trigger.py`` file to the the
shotgunEvents conf file::

    ...
    [plugins]
    # Plugin related settings

    # A comma delimited list of paths where the framework should look for plugins to
    # load.
    paths: /path/to/sg_jira_bridge/sg_events_triggers, /path/to/your/other/shotgun/plugins
    ...

Authentication
--------------
The trigger uses the following environment variables to retrieve Shotgun
credentials::

    # sg_jira_event_trigger.py credentials
    SGDAEMON_SGJIRA_NAME='sg_jira_event_trigger'
    SGDAEMON_SGJIRA_KEY='01234567@abcdef0123456789'  # replace with your api key

.. note::

    The trigger uses it's own authentication to Shotgun, independent of the
    auth used in the SG Jira Bridge Server and the main shotgunEvents settings.
    We highly recommend you add an additional Script User in Shotgun solely
    for this trigger.



Starting Everything Up
**********************
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

- Create an Asset in Shotgun with a TaskTemplate appied.
- Toggle the **Sync In Jira** checkbox ``on`` for one of the Tasks.
- Navigate to your Jira site to see the Issue created for that Task.
- Change the status in Jira to see the status change in Shotgun.

If things don't seem to be working, check the output from SG Jira Bridge and
shotgunEvents in your terminal window for log messages.

.. note::
    For any synced entity, Shotgun stores the associated Jira key in the
    ``sg_jira_key`` field which will update automatically when you initially
    sync the Task. Jira stores the associated Shotgun Entity type and ID in
    the **Shotgun Type** and **Shotgun ID** fields as well as a link to the
    entity in Shotgun in the **Shotgun URL** field. This is a good indicator
    that things are working correctly.

