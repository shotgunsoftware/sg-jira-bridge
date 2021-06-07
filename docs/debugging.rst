Debugging
*********

Logging
=======
The SG-Jira-Bridge uses standard Python logging. The logging configuration is
stored in a ``LOGGING`` *dict* in the ``settings.py`` file and uses the
standard :mod:`logging.config` format.

By default the SG Jira Bridge logs ``INFO`` messages and above which provide
a good amount of detail to audit what is happening with each request.

.. warning::

    If you are troubleshooting or doing development, setting the logging level
    to ``DEBUG`` can be useful. However, this log level is extremely verbose.
    Under normal operation, it is recommended to use ``INFO``.

::

    # Define logging
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        # Settings for the parent of all loggers
        "root": {
            # Set default logging level for all loggers and add the console and
            # file handlers
            "level": "DEBUG",
            "handlers": [
                "console", "file"
            ],
        },
        "loggers": {
            # Set web server level to WARNING so we don't hear about every request
            # If you want to see the requests in the logs, set this to INFO.
            "webapp": {
                "level": "WARNING"
            }
        },
        # Some formatters, mainly as examples
        "formatters": {
            "verbose": {
                "format": "%(asctime)s %(levelname)s [%(module)s %(process)d %(thread)d] %(message)s"
            },
            "standard": {
                "format": "%(asctime)s %(levelname)s [%(module)s] %(message)s"
            },
            "simple": {
                "format": "%(levelname)s:%(name)s:%(message)s"
            },
        },
        # Define the logging handlers
        "handlers": {
            # Print out any message to stdout
            "console": {
                "level": "INFO",
                "class": "logging.StreamHandler",
                "formatter": "standard"
            },
            "file": {
                "level": "INFO",
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "standard",
                # this location should be updated to where you store logs
                "filename": "/tmp/sg_jira.log",
                "maxBytes": 1024 * 1024,
                "backupCount": 5
            },
        },
    }


Testing on a Machine Not Accessible to Jira
===========================================

Installing ngrok
----------------
If you are testing locally, it's likely your machine isn't accessible from the
Jira server (especially if you're using a Jira cloud server). However, you can
use ngrok https://ngrok.com to allow it to securely access your local machine
for testing and development: ``ngrok http 9090``.

To get ngrok running, sign up for a free account at ngrok.com. `Download and
install ngrok <https://ngrok.com/download>`_. If you use a package manager like
`Homebrew <https://brew.sh/>`_, you may be able to install from there as well.

Setup authentication by running ``ngrok authtoken <your auth token>`` where
``<your auth token>`` is the auth token assigned to your ngrok account. You can
get the token from https://dashboard.ngrok.com/auth.

Starting ngrok
--------------
.. code-block:: bash

    $ ngrok http 9090

.. note::
    Each time you start ngrok, it assigns a random hostname to your connection.
    This means you'll need to update the Jira Webhook you setup to point to the
    correct hostname each time. ngrok does have a paid plan that allows
    you to specify the hostname you wish to use.


Common Issues
=============
RuntimeError: maximum recursion depth exceeded
----------------------------------------------
If you are seeing this error in your logs when trying to start the web service,
you may be using an old version the ShotGrid Jira Bridge and need to update.

Atlassian deprecated cookie-based authentication on Jira Cloud which causes the
Jira client library to generate this error. Updating to the latest version of
ShotGrid Jira Bridge transitions the authentication to use Basic Auth.

You will need to generate an API token and use this as your user secret (password).
User passwords are no longer supported by Jira Cloud. See
https://confluence.atlassian.com/x/Vo71Nw for information on how to generate a
token.

Jira Server should be unaffected by this error as it still works with user
passwords and does not support API tokens.

For more information, see: https://developer.atlassian.com/cloud/jira/platform/jira-rest-api-basic-authentication/

Not Seeing Changes Sync
-----------------------
When you make a change in ShotGrid or Jira, the bridge evaluates whether the
change should be synced to to the target site, tries to convert the value to an
acceptable value in the target site, and then submits the change.

If you're not seeing your changes sync across, there are a few things you can
check.

SG Jira Bridge Webapp Isn't Responding
--------------------------------------
You can check to see if the Bridge is running by issuing a GET request for the
sync URL in your browser. Copy the URL you have entered in the
**Jira Sync URL** field in your ShotGrid Project and enter it in your browser.
You should see a message that says something like::

    ShotGrid to Jira
    Syncing with default settings.

If there is no connection:

- Make sure you've started the Sg Jira Bridge
- Verify the URL you entered is in the correct format.
- Ensure you're connecting to the correct port number.

If you see an Error Response, the server is running but your URL may not be
correct. The URL should look like::

    http://<hostname>:<port>/<sg2jira | jira2sg>/<settings_name>

For example: ``http://localhost:9090/sg2jira/my_settings``

ShotGrid changes aren't syncing to Jira
--------------------------------------
The first place to check is in the shotgunEvents log files to see if the
trigger was run and issued a successful call to the SG Jira Bridge.

Next, check the logs for the SG Jira Bridge and see if the request was
received and processed successfully. The logs should make this very apparent.

If you don't see any errors, make sure your Syncer and SyncHandler are
accepting the event for processing.

Other things to check:

- Is your ShotGrid Project configured to sync to Jira?
- Is the Entity type configured to sync to Jira?
- Does the Entity that generated the event enabled for syncing (the **Sync In
  Jira** checkbox field is checked)?

Jira changes aren't syncing to ShotGrid
--------------------------------------
Check the logs for the SG Jira Bridge and see if the request from Jira was
received and processed successfully. The logs should make this very apparent.

If SG Jira Bridge is not receiving the request:

- Check that your Jira Webhook is setup and configured correctly. If you're
  using a local Jira instance, you can also check the logs to see if the
  webhook fired.
- Make sure your SG Jira Bridge is accessible from your Jira server. If you
  are using a Jira Cloud instance and SG Jira Bridge is running inside a
  firewalled environment, you'll need to open up access to the application
  or move SG Jira Bridge into some sort of DMZ setup.


Value can't be translated to a ShotGrid/Jira value
-------------------------------------------------
If you change a status in ShotGrid or Jira and there's no matching status value
defined by the mapping in your handlers for the change, then you will see
something like this in the logs::

    2019-03-11 15:59:09,517 WARNING [entity_issue_handler] Unable to find a matching Jira status for ShotGrid status 'na'

In this case, there is no Jira status defined in the handlers to match with
the ``na`` status in ShotGrid. Your handler defines a
``_sg_jira_status_mapping()`` property that returns the status mapping.
You can see there's no ``na`` status here::

    return {
        "ip": "In Progress",
        "fin": "Done",
        "res": "Done",
        "rdy": "Selected for Development",  # Used to be "To Do" ?
        "wtg": "Selected for Development",
        "hld": "Backlog",
    }


Time Tracking: Original Estimate is Required
--------------------------------------------
If you encounter the following error::

    JIRAError: JiraError HTTP 400 url: https://myjira.atlassian.net/rest/api/2/issue
	    text: Time Tracking: Original Estimate is required.

This means you have Time Tracking enabled on your Jira site and set as a
required field. However, Time Tracking is not on your default Issue creation
screen.

**Solution**

Add Time Tracking to the default Issue creation screen for this project and
this error should be resolved.
