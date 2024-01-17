# Contributing to the Flow Production Tracking Jira Bridge

### Overview

Flow Production Tracking Jira Bridge is an open source project.

This project accepts and greatly appreciates contributions.
The project follows the [fork & pull](https://help.github.com/articles/using-pull-requests/#fork--pull) model for accepting contributions.

When contributing code, please follow the following process:
* Familiarize yourself with the coding style of the project
   * The project follows most PEP-8 recommendations with the exception of line length
   * The project is documented using Sphinx docstrings in code and with markdown in the GitHub wiki
   * Code logic must be tested by unit tests
* Optionally start an Intent-to-implement GitHub issue to discuss the change you are looking to make
* Fork the repo and create a branch off of the master branch
   * The name of your branch should should be indicative of the change you are making and should include the issue number if applicable
   * An example branch name could be `bugs/fix-link-field-updates-on-delete-103`
* Create a pull request (and reference the issue if created)
   * The description of the pull request should describe in detail the change being made. It should be possible to understand all aspects of the change from the PR description without having to read code
* Flow Production Tracking developers will provide feedback on pull requests
   * The developers will look at code quality, style, tests, performance, maintainability, and directional alignment with the goals of the project
   * Code that implements behavior considered not appropriate for general use will be send back for updates
* For code to be accepted, you must have a signed [individual](pdfs/ind_contrib_agmt_forshotgun_jira_bridge.pdf) or [corporate](pdfs/corp_contrib_agmt_forshotgun_jira_bridge.pdf) contribution agreement

### Commit Messages

Please format commit messages as follows (based on [A Note About Git Commit Messages](http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html)):

```text
Summarize change in 50 characters or less

Provide more detail after the first line. Leave one blank line below the
summary and wrap all lines at 72 characters or less.

If the change fixes an issue, leave another blank line after the final
paragraph and indicate which issue is fixed in the specific format
below.

Fix #42
```

Also do your best to factor commits appropriately, not too large with unrelated things in the same commit, and not too small with the same small change applied N times in N different commits.

### Notes

If you have made significant contributions to this project and are interested in becoming a maintainer, email ems.shotgrid.team.eng@autodesk.com.
