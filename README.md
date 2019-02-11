# sg-jira-bridge

A simple synchronization setup between Shotgun and Jira.


- **sg_jira_event_trigger.py**: A Shotgun event trigger which can be used with the [Shotgun Event Daemon](https://github.com/shotgunsoftware/shotgunEvents)
- **webapp.py**: A simple web app used as a frontend for the synchronisation.
- **service.py**: A script to run the web app as a service on Linux and MacOS platforms.
- **win_service.py**:  (TODO) A script to run the web app as a service on Windows.
- **sg_jira**: Python package for handling the synchronization between Shotgun and Jira.

Table of contents
=================


* [JIRA Setup](#jira-setup)
* [Shotgun Setup](#shotgun-setup)
    * [Project](#project)
    * [All Entity Types to be Synced](#all-entity-types-to-be-synced)
* [Running the setup locally for testing](#running-the-setup-locally-for-testing)
    * [Install required packages](#install-required-packages)
        * [Using pip](#using-pip)
        * [Using pipenv](#using-pipenv)
    * [Settings](#settings)
        * [Authentication](#authentication)
        * [Logging](#logging)
        * [Sync settings](#sync-settings)
    * [Setting up the Shotgun Event Daemon trigger](#setting-up-the-shotgun-event-daemon-trigger)
        * [Install required Python modules](#install-required-python-modules)
            * [pip](#pip)
            * [pipenv](#pipenv)
    * [Setting up the Jira webhook](#setting-up-the-jira-webhook)
        * [ngrok](#ngrok)
        * [Jira](#jira)
    * [Starting everything up](#starting-everything-up)
        * [ngrok](#starting-ngrok)
        * [SG Jira Bridge Web Server](#starting-the-sg-jira-bridge-web-server)
        * [Shotgun Event Daemon](#starting-the-shotgun-event-daemon)
* [Unit tests and CI](#unit-tests-and-ci)
    

# Jira setup

The following Issue fields must be created in Jira and made available in Boards:

- `Shotgun Type`
- `Shotgun Id`  
- `Shotgun URL`

# Shotgun setup

The following fields must be created in Shotgun:

## Project
- **Jira Sync Url** - `sg_jira_sync_url` (_File/Link_)
- **Jira Key** - `sg_jira_key` (_Text_)

Any Project you want to enable for syncing should have the **Jira Sync Url** value set to `http://<server host>:9090/<settings name>/sg2jira`.  
Where `<server host>` is the host of the SG Jira Bridge web server and `<settings name>` is the name of the settings defined in your settings file.  
For example, if you're running a server on _localhost_ and using settings named _default_, you would enter `http://localhost:9090/default/sg2jira`

## All Entity Types to be Synced
- **Jira Type** - `sg_jira_type` (_Text_)
- **Jira Key** - `sg_jira_key` (_Text_)


Entities will only be synced if they have a **Jira Key** value and are linked to a Project. 



# Running the setup locally for testing

## Install required packages

**Python 2.7** is required.

You may install the required packages using `pip` or `pipenv`.
 
### Using pip

 A _requirements.txt_ file is provided to install all required packages. 
 
 
```bash
# create a virtualenv
$ virtualenv venv

# Activate the virtualenv
# On MacOS/Linux:
$ source venv/bin/activate
# On Windows (using PowerShell)
$ venv/Scripts/activate

# Install required packages
pip install -r requirements.txt

```

### Using pipenv
Alternately, if you're using `pipenv` (https://pipenv.readthedocs.io) follow these instructions:

```bash
# create a virtualenv (the shell will be activated automatically)
$ pipenv --python 27

# Install the required packages
$ pipenv install
```
This will install everything specified in the `requirements.txt` and generate a `Pipfile` and `Pipfile.lock`. 
    
If you already have a `Pipfile` or `Pipfile.lock` you can specify you wish to import the contents of the _requirements.txt_ file with 

```bash
$ pipenv install -r path/to/requirements.txt
```

## Settings
Settings are defined in the `settings.py` file in the root of the repo. Since the settings are stored in a Python file, it allows for a lot of flexiblity to adapt to your specific environment requirements if needed. The settings file contains three main sections:

### Authentication
  
Credentials are retrieved by default from environment variables:
 
 - `SGJIRA_SG_SITE`: the Shotgun site url (_https://mysite.shotgunstudio.com_).
 - `SGJIRA_SG_SCRIPT_NAME`: a Shotgun script user name (_sg-jira-sync_)
 - `SGJIRA_SG_SCRIPT_KEY`: the Shotgun script user Application Key (_rrtOzkn@pkwlhak5witgugjdd_)
 - `SGJIRA_JIRA_SITE`: the Jira server url (_https://mystudio.atlassian.net_)
 - `SGJIRA_JIRA_USER`: the system name of the Jira user used to connect for the sync (_richard.hendricks@piedpiper.com_)  This is usually the email address you sign in to Jira with. Jira does not have a concept of a "script" user so this will need to be the designated user account that will control the sync updates. It will need appropriate permissions to make any changes required.
 - `SGJIRA_JIRA_USER_SECRET`: the Jira user password (_youkn0wwh@tapa$5word1smAKeitag0odone3_)
 
You may set these in your environment. However for testing, we recommend installing [dotenv](https://pypi.org/project/python-dotenv) (included in the _requirements.txt_) and defining these in a `.env` file. 

```
# Shotgun credentials
SGJIRA_SG_SITE='https://mysite.shotgunstudio.com'
SGJIRA_SG_SCRIPT_NAME='sg-jira-bridge'
SGJIRA_SG_SCRIPT_KEY='01234567@abcdef0123456789'

# Jira credentials
SGJIRA_JIRA_SITE='https://mystudio.atlassian.net'
SGJIRA_JIRA_USER='richard.hendricks@piedpiper.com'
SGJIRA_JIRA_USER_SECRET='youkn0wwh@tapa$5word1smAKeitag0odone3'
```

### Logging

The SG-Jira-Bridge uses standard Python logging. The logging configuration is stored in a `LOGGING` _dict_ [using the standard `logging.config` format](https://docs.python.org/2/library/logging.config.html#module-logging.config)

### Sync Settings

The sync settings are stored in a `SYNC` _dict_ in the format:

```python
SYNC = {
    "my_settings": {
        # The syncer class to use
        "syncer": "sg_jira.MyCustomSyncer",
        # And the specific settings which are passed to its __init__() method
        "settings": {
            "my_setting_name": "My Setting Value"
        },
    }
}
```

Custom syncers can be referenced in the settings file with their module path and their specific
settings.

For example:
```python
# Additional paths can be added for custom syncers
sys.path.append(os.path.abspath("./examples"))

SYNC = {
    "default": {
        # The syncer class to use
        "syncer": "sg_jira.TaskIssueSyncher",
        # And the specific settings which are passed to its __init__() method
        "settings": {
            "foo": "blah"
        },
    },
    "test": {
        # Example of a custom syncer with an additional parameter to define
        # a log level.
        "syncer": "example_sync.ExampleSync",
        "settings": {
            "log_level": logging.DEBUG
        },
    }
}
```


## Setting up the Shotgun Event Daemon trigger

The [Shotgun event daemon](https://github.com/shotgunsoftware/shotgunEvents) is used to poll events from Shotgun and dispatch them to the trigger that initiates the sync to Jira for that event. 

- Install the Shotgun event daemon from https://github.com/shotgunsoftware/shotgunEvents (instructions are available in the repo)
- Once it's installed correctly, copy the `sg_jira_event_trigger.py` file to the directory configured for your triggers

The trigger uses the following environment variables to retrieve Shotgun credentials:

- `SGDAEMON_SGJIRA_NAME`: a Shotgun script user name
- `SGDAEMON_SGJIRA_KEY`: the Shotgun script user application key.

_Note: The trigger uses it's own authentication to Shotgun, independent of the auth used in the SG Jira Bridge Server. We highly recommend you add an additional Script User in Shotgun solely for this trigger and use those auth details here._

### Install required Python modules

The shotgunEventDaemon requires the [Shotgun Python API](https://github.com/shotgunsoftware/python-api). 
The trigger requires the [`requests` module](http://docs.python-requests.org). 

We recommend creating a virtual env. However, you can skip this if you decide to install the packages globally or from your existing library. 

The easiest way to install the required packages is using `pip` or `pipenv`.
 
#### pip

```bash
# create a virtualenv
$ virtualenv venv

# Activate the virtualenv
# On MacOS/Linux:
$ source venv/bin/activate
# On Windows (using PowerShell)
$ venv/Scripts/activate

# Install required packages
pip install requests https://github.com/shotgunsoftware/python-api/archive/v3.0.37.zip

```

#### pipenv
Alternately, if you're using `pipenv` (https://pipenv.readthedocs.io) follow these instructions:

```bash
# create a virtualenv (the shell will be activated automatically)
$ pipenv --python 27

# Install the required packages
$ pipenv install requests https://github.com/shotgunsoftware/python-api/archive/v3.0.37.zip
```

## Setting up the Jira webhook

SG Jira Bridge uses the jira webhooks to respond to updates from Jira. When an event occurs that requires a sync to Shotgun, the webhook fires and notifies the SG Jira Bridge server, which then updates Shotgun. You need to configure Jira to point to your SG Jira Bridge server address and respond to the right event types.


### ngrok

When testing locally, it likely your machine isn't accessible from the Jira server (especially if you're using a Jira cloud server). However, you can use ngrok https://ngrok.com to allow it to securely access your local machine for testing: `ngrok http 9090`.

- Sign up for a free account at ngrok.com
- Download and install ngrok ([detailed instructions here](https://ngrok.com/download)). If you use a package manager like [Homebrew](https://brew.sh/), you may be able to install from there as well.
- run `ngrok authtoken <your auth token>` where `<your auth token>` is the auth token assigned to your ngrok account. You can get the token from https://dashboard.ngrok.com/auth

### Jira

- Navigate to the Jira system settings (_Settings > System > WebHooks_)
- Click "Create Webhook"
- Add the following values:
    - **Name**: eg. "SG Jira Bridge Test"
    - **URL**: eg. `https://c66cdcc6.ngrok.io/jira2sg/default/issue/${issue.key}`.  
    URL in the form `<fqdn>/jira2sg/<settings name>/issue/${issue.key}`. This will be the address of the server running on your machine with the name of the settings you're using in the path.
        - `<fqdn>`: The scheme, host and domain name for your server. If using ngrok, it should match the value that ngrok assigned when you started it (eg. https://c66cdcc6.ngrok.io)
        - `<settings name>`: The name of the settings to use from your `settings.py` file. (eg. default)
        - `${issue.key}`: this is a Jira token variable and should be entered as it is here.
    - **Description**: (optional) eg. "Webhook that syncs Jira data with Shotgun using the SG Jira Bridge"
    - **Events**
        - **JQL**: eg. `project = "My test project"`  
        You can specify a JQL query to restrict the webhook to a particular project if you have multiple projects in Jira and you only want specific projects to sync with Shotgun
        - **Issue Related Events**  
        Check only the specified events listed below
            - ✅ Issue: created
            - ✅ Issue: updated
            - ✅ Issue: deleted  
    
    
    - **Exclude Body**: This must be **unchecked** in order for the required JSON payload to be delivered

## Starting Everything Up

### Starting ngrok

```
ngrok http 9090
```
_**Note**: Each time you start ngrok, it assigns a random hostname to your connection. This means you'll need to update the Jira Webhook you setup to point to the correct hostname each time. ngrok does have a paid plan that allows you to specify the hostname you wish to use, but that's up to you. 😄_

### Starting the SG Jira Bridge Web Server

```
python webapp.py --settings <path to your settings> --port 9090
```

### Starting the Shotgun Event Daemon

```
./shotgunEventDaemon.py start
```

# Unit tests and CI
Unit tests are in the `/tests` folder and can be run with `python run_tests.py`.

[Azure Pipelines](https://github.com/marketplace/azure-pipelines) are used for the continuous integration and run the following validations:

- Enforce reasonable PEP-8 conventions with Flake8.
- Run unit tests on Linux, Mac and Windows with Python 2.7.

Azure Pipelines jobs are defined by the description files in the `/azure-pipelines` folder.
