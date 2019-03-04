# sg-jira-bridge

A simple synchronization setup between Shotgun and Jira.


-  **sg_jira_event_trigger.py**: A Shotgun event trigger which can be used with the [Shotgun Event Daemon](https://github.com/shotgunsoftware/shotgunEvents)
- **webapp.py**: A simple web app used as a frontend for the synchronisation.
- **service.py**: A script to run the web app as a service on Linux and MacOS platforms.
- **win_service.py**:  (TODO) A script to run the web app as a service on Windows.
- **sg_jira**: Python package for handling the synchronization between Shotgun and Jira.


## Jira setup

The "Shotgun Type" and "Shotgun Id" custom string fields need to be added to Issues in Jira
and made available in Boards. 

## Shotgun setup
- A "Jira Sync Url" File/Link field (`sg_jira_sync_url`) must be added to Projects, and the URL set to `http://<server host>/<settings name>/sg2jira`.
- A "Jira Id" string field (`sg_jira_id`) must be added to Shotgun Projects. Entities will only be synced if they have a "Jira Id" value and are linked to a Project.
- "Jira Type" (`sg_jira_type`) and "Jira Id" (`sg_jira_id`) text fields need to be added to any Shotgun Entity types you want to be synced.

## Running the setup locally for testing
 
 ### Setting up Shotgun and Jira credentials
 
 Credentials are retrieved by default from environment variables:
 - SGJIRA_SG_SITE: the Shotgun site url.
 - SGJIRA_SG_SCRIPT_NAME: a Shotgun script user name.
 - SGJIRA_SG_SCRIPT_KEY: the Shotgun script user secret key.
 - SGJIRA_JIRA_SITE: the Jira server url.
 - SGJIRA_JIRA_USER: a Jira user system name (not a display name).
 - SGJIRA_JIRA_USER_SECRET: the Jira user password.
 
 These values can be defined in a `.env` file if https://pypi.org/project/python-dotenv is installed on your machine. 
 
 ### Running the web app:
 A _requirements.txt_ file is provided to install all required packages. 
 The web app can be run from the command line with Python 2.7:
 - Create a virtualenv: `virtualenv venv`.
 - Activate the virtualenv: `source venv/bin/activate`.
   - On Windows `venv/Scripts/activate` in a Power shell.
- Install needed packages: `pip install -r requirements.txt`.
- Run the web app: `python webapp.py --settings <path to your settings> --port 9090`

### Setting up the event daemon trigger
Install the Shotgun event daemon https://github.com/shotgunsoftware/shotgunEvents and copy
the  `sg_jira_event_trigger.py` file in a place where the event daemon can find it.

The trigger uses the following environment variables to retrieve Shotgun credentials:
- SGDAEMON_SGJIRA_NAME: a Shotgun script user name.
- SGDAEMON_SGJIRA_KEY: the Shotgun script user secret key.

Add a _Jira Sync Url_ File/Link field (system name `sg_jira_sync_url`) to Projects in Shotgun and set it to `http://localhost:9090/sg2jira/default`
on the Project you want to use for your tests.

### Setting up the Jira webhook

If using a cloud Jira server, you can use ngrok https://ngrok.com to allow it to access your
local machine: `ngrok http 9090`.

Go to the Jira system settings and enable a webhook target with something like: `https://c66cdcc6.ngrok.io/jira2sg/default/issue/${issue.key}`

Subscribe to Issue created, deleted, updated events and make sure that Exclude body is **not** on.
You can restrict the webhook to a particular Jira project by having a JQL query like `project = "My test project"`

## Custom syncing logic

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
        # And its specific settings which are passed to its __init__ method
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

## Unit tests and CI
Unit tests are in the _tests_ folder and can be run with `python run_tests.py`.

[Azure Pipelines](https://github.com/marketplace/azure-pipelines) are used for the continuous integration and run the following validations:
- Enforce reasonable PEP-8 conventions with Flake8.
- Run unit tests on Linux, Mac and Windows with Python 2.7.

Azure Pipelines jobs are defined by the description files in the _azure-pipelines_ folder.

## Contributing

This project welcomes contributions. Please see our contribution guide at [CONTRIBUTING.md](CONTRIBUTING.md)
