[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Linting](https://img.shields.io/badge/PEP8%20by-Hound%20CI-a873d1.svg)](https://houndci.com)
[![Python 3.9](https://img.shields.io/badge/python-3.9-blue.svg)](https://www.python.org/)

# ShotGrid Jira Bridge

ShotGrid Jira Bridge is a simple synchronization setup between ShotGrid and Jira. It's designed to get you up and running quickly with basic sync functionality for Tasks, Issues, and Notes.

By extending the base syncer and sync handlers you can quickly build custom workflows to connect your ShotGrid and Jira sites. Details like entity types, hierarchy, issue types, fields, statuses, and logic can all be custom defined to match your studio's workflow.

![alt text](https://developer.shotgridsoftware.com/sg-jira-bridge/_images/sg_jira_bridge_workflow.png "SG Jira Bridge Overview")

# Components

- **`triggers/sg_jira_event_trigger.py`**: A ShotGrid event trigger which can be used with the [ShotGrid Event Daemon](https://github.com/shotgunsoftware/shotgunEvents)
- **`webapp.py`**: A simple web app used as a frontend for the synchronization.
- **`service.py`**: A script to run the web app as a service on Linux and MacOS platforms.
- **`win_service.py`**:  (TODO) A script to run the web app as a service on Windows.
- **`sg_jira`**: Python package for handling the synchronization between ShotGrid and Jira.

# Documentation

Full documentation is available at https://developer.shotgridsoftware.com/sg-jira-bridge

# Requirements

- Python 3.9
- A [ShotGrid](https://shotgridsoftware.com) site
- A [Jira](https://www.atlassian.com/software/jira) site

# Building the Docs
The documentation is built with [Sphinx](http://www.sphinx-doc.org) and is located in the `docs/` folder. To build the html output for the docs:

```bash
$ pip install -U sphinx sphinx-rtd-theme
$ cd docs
$ make html
```


# Contributing

This project welcomes contributions. Please see our contribution guide at
[CONTRIBUTING.md](CONTRIBUTING.md)
