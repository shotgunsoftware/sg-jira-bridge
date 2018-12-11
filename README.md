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
- A "Jira Id" string field must be added to Shotgun Projects. Only Entities under a Project with a value set will be synced. 
- "Jira Type" and "Jira Id" custom string fields need to be added to Shotgun Entities meant to be synced.

## Running the setup locally for testing
 
 A _requirements.txt_ file is provided to install all needed packages. 
 The web app can be run from the command line with Python 2.7:
 - Create a virtualenv: `virtualenv venv`.
 - Activate the virtualenv: `source venv/bin/activate`.
   - On Windows `venv/Scripts/activate` in a Power shell.
- Install needed packages: `pip install -r requirements.txt`.
- Run the web app: `python webapp.py --settings <path to your settings> --port 9090`

## Custom syncing logic

Custom syncers can be referenced in the settings file with their module path and their specific
settings.
For example:
```
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

[Azure Pipelines](https://github.com/marketplace/azure-pipelines) are used for the continuous integration and run the following validation:
- Enforce PEP-8 conventions with Flake8.
- Run unit tests on Linux, Mac and Windows with Python 2.7.

Azure Pipelines jobs are defined by the description files in the _azure-pipelines_ folder.
