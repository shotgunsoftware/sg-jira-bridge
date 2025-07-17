# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import logging
import os

import requests

# Allow users to define their sensitive data in a .env file and
# load it in environment variables with python-dotenv.
# https://pypi.org/project/python-dotenv/
from dotenv import load_dotenv
from six.moves import urllib

load_dotenv(override=True)

"""
A Flow Production Tracking event daemon plugin which sends all events to the PTR/Jira bridge.

Flow Production Tracking Projects are associated with a Jira sync server by specifying an url in the
custom `sg_jira_sync_url` field.
"""

# These events potentially modify the PTR schema
SCHEMA_CHANGE_EVENT_TYPES = [
    "Shotgun_DisplayColumn_New",
    "Shotgun_DisplayColumn_Change",
    "Shotgun_DisplayColumn_Retirement",
    "Shotgun_Status_New",
    "Shotgun_Status_Change",
    "Shotgun_Status_Retirement",
]


def registerCallbacks(reg):
    """
    Register all necessary or appropriate callbacks for this plugin.

    Flow Production Tracking credentials are retrieved from the `SGDAEMON_SGJIRA_NAME` and `SGDAEMON_SGJIRA_KEY`
    environment variables.

    :param reg: A Flow Production Tracking Event Daemon Registrar instance.
    """
    # Narrow down the list of events we pass to the bridge
    event_filter = {
        "Shotgun_Note_Change": ["*"],
        "Shotgun_Task_Change": ["*"],
        "Shotgun_Ticket_Change": ["*"],
        "Shotgun_Project_Change": ["*"],
        "Shotgun_Asset_Change": ["*"],  # Needed by the Asset/Task example.
        "Shotgun_TimeLog_Change": ["*"],  # Needed by the Timelog/Task example.
        # These events require a reset of the bridge to ensure our cached schema
        # is up to date.
        "Shotgun_DisplayColumn_New": ["*"],
        "Shotgun_DisplayColumn_Change": ["*"],
        "Shotgun_DisplayColumn_Retirement": ["*"],
        "Shotgun_Status_New": ["*"],
        "Shotgun_Status_Change": ["*"],
        "Shotgun_Status_Retirement": ["*"],
    }
    # Define a dictionary which is persisted by the framework and will collect
    # routing from Shotgun Projects.
    dispatch_routes = {}
    reg.registerCallback(
        os.environ["SGDAEMON_SGJIRA_NAME"],
        os.environ["SGDAEMON_SGJIRA_KEY"],
        process_event,
        event_filter,
        dispatch_routes,
        stopOnError=False,
    )

    # Set the logging level for this particular plugin. Let debug and above
    # messages through (don't block info, etc). This is particularly useful
    # for enabling and disabling debugging on a per plugin basis.
    reg.logger.setLevel(logging.DEBUG)


def process_event(sg, logger, event, dispatch_routes):
    """
    A callback which posts Jira sync requests.

    :param sg: Flow Production Tracking API handle.
    :param logger: Logger instance.
    :param event: A Flow Production Tracking EventLogEntry entity dictionary.
    :param dispatch_routes: A dictionary where keys are PTR Project ids and values urls.
    """
    logger.debug("Processing %s" % event)
    if event.get("event_type") in SCHEMA_CHANGE_EVENT_TYPES:
        # A schema change has occurred. Clear the dispatch routes so that
        # the next time an event is processed for a Project, the bridge will
        # be reset, clearing the schema cache.
        # TODO: We blindly clear all routes for all Projects here. If two
        # different webapps are being used, they will both be unnecessarily
        # cleared. Possibly be smarter and only clear the routes for the
        # affected Projects.
        dispatch_routes.clear()
        logger.debug("Cleared dispatch_routes")
        logger.debug("Event successfully processed.")
        return

    # Sometimes rogue events caused by Shotgun server updates and maintenance are retrieved by the
    # event daemon: this is why we use a `get` in various places instead of
    # accessing data with the expected key directly.
    if event.get("event_type") == "Shotgun_Project_Change":
        # Check if the sg_jira_sync_url field was modified.
        if event.get("attribute_name") == "sg_jira_sync_url":
            entity = event.get("entity")
            if entity and entity["id"] in dispatch_routes:
                # Just clear the cache which will be re-populated later.
                del dispatch_routes[entity["id"]]
        return

    # Check the Project and get the routing
    project = event.get("project")
    # If there is no Project associated with the event, just ignore it
    if not project:
        logger.debug("Ignoring event %s not associated with any Project" % event)
        return

    sync_server_url = _get_dispatch_route(sg, logger, project, dispatch_routes)
    if not sync_server_url:
        logger.debug("Ignoring Jira sync for Project %d" % project["id"])
        return

    # Build the payload from the event metadata
    # TODO: We should mimic the payload sent by Shotgun webhooks
    #    {
    #      "id": 5,
    #      "meta": {
    #        "type": "attribute_change",
    #        "entity_id": 1402,
    #        "new_value": "helloasdasd",
    #        "old_value": "hello",
    #        "entity_type": "Asset",
    #        "attribute_name": "code",
    #        "field_data_type": "text"
    #      },
    #      "user_id": 88,
    #      "entity_id": 1402,
    #      "operation": "update",
    #      "user_type": "HumanUser",
    #      "created_at": "2018-12-20 20:35:15.61203",
    #      "project_id": 86,
    #      "entity_type": "Asset"
    #    }
    meta = event["meta"]
    entity_type = meta.get("entity_type")
    entity_id = meta.get("entity_id")
    if not entity_type or not entity_id:
        logger.debug("Ignoring event. Invalid Entity meta data %s." % event)
        return
    payload = {
        "meta": meta,
        "session_uuid": event.get("session_uuid"),
        "user": event.get("user"),
        "project": event["project"],
        "entity_type": entity_type,
        "entity_id": entity_id,
    }

    # Just send a POST request with the event meta data as payload.
    sync_url = "%s/%s/%d" % (
        sync_server_url,
        payload["entity_type"],
        payload["entity_id"],
    )
    logger.debug("Posting event %s to %s" % (payload["meta"], sync_url))
    # Post application/json request
    response = requests.post(
        sync_url,
        json=payload,
    )
    response.raise_for_status()
    logger.debug("Event successfully processed.")


def _get_dispatch_route(sg, logger, project, dispatch_routes):
    """
    Return the sg-jira-bridge sync url for the given Project.

    :param sg: Flow Production Tracking API handle.
    :param logger: Logger instance.
    :param list project: A Flow Production Tracking Project entity dictionary.
    :param dict dispatch_routes: A mapping of PTR Project ids to sync urls.
    :returns: Sync url as a string or ``None``.
    """
    # Shotgun requests are costly so we cache Projects dispatch routes and re-use
    # them when we treat an event for a Project we handled before.
    if project["id"] not in dispatch_routes:
        # This is the first time we're treating an event for this Project, get the
        # routing, if any, from Shotgun.
        logger.info("Retrieving sync routing for Project %d" % project["id"])
        sg_project = sg.find_one(
            "Project", [["id", "is", project["id"]]], ["name", "sg_jira_sync_url"]
        )
        if not sg_project:
            # This shouldn't happen, but better to be safe here.
            logger.warning(
                "Unable to find a Shotgun Project "
                "with id %d, skipping event..." % (project["id"])
            )
            dispatch_routes[project["id"]] = None
            return

        sync_url = _get_project_sync_url(sg_project.get("sg_jira_sync_url"), logger)
        dispatch_routes[sg_project["id"]] = sync_url

        # We reset the schema cache the very first time we treat a route.
        # This enables:
        #   - Resetting the schema cache if the event daemon is restarted,
        #     without having to restart the web app.
        #   - Triggering a schema cache reset by emptying the
        #     dispatch_routes cache when a schema change is detected in Shotgun.
        if sync_url:
            _reset_bridge(sync_url, logger)

    return dispatch_routes[project["id"]]


def _get_project_sync_url(sg_field_value, logger):
    """
    Return sync url from Flow Production Tracking File/Link field.

    :param sg_field_value: Flow Production Tracking File/Link field value as a dict or ``None``.
    :param logger: Logger instance.
    :returns: URL for sync as a str or ``None``.
    """
    # We expect a File/Link field with a web link, something like:
    # {
    #    'name': 'PTR Jira Bridge',
    #    'url': 'http://localhost:9090',
    #    'content_type': None,
    #    'type': 'Attachment',
    #    'id': 123456,
    #    'link_type': 'web'
    #
    # }
    # Default value if we can't retrieve a valid value
    sync_url = None
    if isinstance(sg_field_value, dict):
        if sg_field_value.get("link_type") == "web":
            sync_url = sg_field_value.get("url")
            if sync_url and sync_url.endswith("/"):
                sync_url = sync_url[:-1]

    # There is a value in the sg_field_value but it's not what we expect.
    if sync_url is None and sg_field_value:
        logger.warning(
            "Sync URL could not be extracted from %s. Expected a dictionary "
            "representing a web link like {'link_type': 'web', 'url': "
            "'https://<servername>/sg2jira/<settingsname>'}" % sg_field_value
        )

    return sync_url


def _reset_bridge(server_url, logger):
    """
    Reset the Jira bridge

    :param str server_url: Sync URL of the PTR Jira Bridge.
    :param logger: Logger instance.
    """
    # The url is for the sync and contains a direction and settings name.
    # We only need the server for our request.
    parsed_url = urllib.parse.urlparse(server_url)
    if not parsed_url.scheme or not parsed_url.netloc:
        logger.debug(
            "Failed to reset Jira Bridge. Unable to extract server address "
            "from %s." % server_url
        )
        return

    reset_url = "%s://%s/admin/reset" % (parsed_url.scheme, parsed_url.netloc)
    logger.debug("Posting to %s" % reset_url)
    response = requests.post(reset_url)
    response.raise_for_status()
    logger.debug("Jira Bridge reset.")
