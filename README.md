[![Supported Python versions: 3.9, 3.10, 3.11, 3.13](https://img.shields.io/badge/Python-3.9_|_3.10_|_3.11_|_3.13-blue?logo=python&logoColor=f5f5f5)](https://www.python.org/ "Supported Python versions")
[![Reference Documentation](http://img.shields.io/badge/doc-reference-blue.svg)](http://developers.shotgridsoftware.com/sg-jira-bridge)

[![Build Status](https://dev.azure.com/shotgun-ecosystem/ShotGrid%20Jira%20Bridge/_apis/build/status/shotgunsoftware.sg-jira-bridge?branchName=master)](https://dev.azure.com/shotgun-ecosystem/ShotGrid%20Jira%20Bridge/_build/latest?definitionId=119&branchName=master)
[![Coverage Status](https://codecov.io/gh/shotgunsoftware/sg-jira-bridge/branch/master/graph/badge.svg)](https://codecov.io/gh/shotgunsoftware/sg-jira-bridge)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# Flow Production Tracking Jira Bridge

Flow Production Tracking Jira Bridge is a simple synchronization setup between Flow Production Tracking and Jira. It's designed to get you up and running quickly with basic sync functionality for Tasks, Issues, and Notes.

By extending the base syncer and sync handlers you can quickly build custom workflows to connect your Flow Production Tracking and Jira sites. Details like entity types, hierarchy, issue types, fields, statuses, and logic can all be custom defined to match your studio's workflow.

![alt text](https://developers.shotgridsoftware.com/sg-jira-bridge/_images/sg_jira_bridge_workflow.png "PTR Jira Bridge Overview")

# Components

- **`triggers/sg_jira_event_trigger.py`**: A Flow Production Tracking event trigger which can be used with the [Flow Production Tracking Event Daemon](https://github.com/shotgunsoftware/shotgunEvents)
- **`webapp.py`**: A simple web app used as a frontend for the synchronization.
- **`service.py`**: A script to run the web app as a service on Linux and MacOS platforms.
- **`win_service.py`**:  (TODO) A script to run the web app as a service on Windows.
- **`sg_jira`**: Python package for handling the synchronization between Flow Production Tracking and Jira.

# Documentation

Full documentation is available at https://developers.shotgridsoftware.com/sg-jira-bridge

# Requirements

- Python - supported versions: `3.9`, `3.10`, `3.11`, `3.13`
- A [Flow Production Tracking](https://autodesk.com/products/flow-production-tracking) site
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
