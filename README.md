# sg-jira-bridge

A simple synchronization setup between Shotgun and Jira.


-  **sg_jira_event_trigger.py**: A Shotgun event trigger which can be used with the [Shotgun Event Daemon](https://github.com/shotgunsoftware/shotgunEvents)
- **webapp.py**: A simple web app used as a frontend for the synchronisation.
- **service.py**: A script to run the web app as a service on Linux and Osx platforms.
- **win_service.py**:  (TODO) A script to run the web app as a service on Windows.
- **sg_jira**: Python package for handling the synchronization between Shotgun and Jira.

## Unit tests and CI
Unit tests are in the _tests_ folder and can be run with `python run_tests.py`.

[Azure Pipelines](https://github.com/marketplace/azure-pipelines) are used for the continuous integration and run the following validation:
- Enforce PEP-8 conventions with Flake8.
- Run unit tests on Linux, Mac and Windows with Python 2.7.

Azure Pipelines jobs are defined by the description files in the _azure-pipelines_ folder.
