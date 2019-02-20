.. _installation:


Installation & Configuration
########################################

Requirements
---------------------------------

note::
    These docs are primarily centered around testing, and not for production
    use. For production use we recommend employing standard production-level
    techniques that are (currently) beyond the scope of these docs.

Python
~~~~~~~~~~~~~~~~~~~~~~
Python 2.7 is required.

JIRA Setup
~~~~~~~~~~~~~~~~~~~~~~
The following Issue fields must be created in Jira and made available in Boards:

- **Shotgun Type**
- **Shotgun ID**
- **Shotgun URL**

Shotgun setup
~~~~~~~~~~~~~~~~~~~~~~
The following fields must be created in Shotgun:

Project
=================================

- **Jira Sync Url** ``sg_jira_sync_url`` *File/Link*
    - ``<server url>`` is the base URL of the SG Jira Bridge web server.
    - ``<settings name>`` is the name of the settings to be used from your settings file.

    *http://<server url>:9090/sg2jira/<settings name>*

    For example, if you're running a server on *sgjirabridge.piedpiper.com* and using settings named *default*, you
    would enter *http://sgjirabridge.piedpiper.com:9090/sg2jira/default*

- **Jira Key** ``sg_jira_key`` *Text*
    This is the Key value of your Project in Jira. For example, ``ABC``


Any Entity
=================================
- **Jira Key** ``sg_jira_key`` *Text*
    Entities will only be synced if they have a **Jira Key** value and are linked to a Project. 


Shotgun Event Daemon
---------------------------------
Link to shotgunEvents and hey your on your own

Installation
---------------------------------
We recommend `setting up a virtual environment <https://docs.python-guide.org/dev/virtualenvs/>`_ for doing testing. 
You may install the required packages using ``pip`` or ``pipenv``. 
 
Using pip
~~~~~~~~~~~~~~~~~~~~~~
Ensure you have `virtualenv <https://pypi.org/project/virtualenv/>`_ installed in your global Python installation.

A ``requirements.txt`` file is provided to install all required packages. 
 
::

    # create a virtualenv
    $ virtualenv venv

    # Activate the virtualenv
    # On MacOS/Linux:
    $ source venv/bin/activate
    # On Windows (using PowerShell)
    $ venv/Scripts/activate

    # Install required packages
    pip install -r requirements.txt


Using pipenv
~~~~~~~~~~~~~~~~~~~~~~
Alternately, if you're using `pipenv <https://pipenv.readthedocs.io>`_ follow these instructions:

::

    # create a virtualenv (the shell will be activated automatically)
    # if python is not in your PATH, you can use pipenv --python /path/to/python/2.7
    $ pipenv --python 2.7

    # Install the required packages
    $ pipenv install

This will install everything specified in the ``requirements.txt`` and generate a ``Pipfile`` and ``Pipfile.lock``. 
    
If you already have a ``Pipfile`` or ``Pipfile.lock`` you can specify you wish to import the contents of the ``requirements.tx`` file with:: 

    $ pipenv install -r path/to/requirements.txt


Copy trigger to shotgunEvents plugin folder

Configuration
---------------------------------

Settings
~~~~~~~~~~~~~~~~~~~~~~
    Authentication
    Logging
    Sync settings

Jira Webhook
~~~~~~~~~~~~~~~~~~~~~~


Startup
########################################

    SG Jira Bridge Web Server
    Shotgun Event Daemon

