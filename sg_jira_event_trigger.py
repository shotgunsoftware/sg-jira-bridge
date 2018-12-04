# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import logging
import requests

"""
A simple Shotgun event daemon plugin which sends all events to the SG/Jira bridge.

Shotgun Projects are associated with a Jira sync server by specifying an url in the
custom `sg_jira_sync_url` field.
"""


def registerCallbacks(reg):
    """
    Register all necessary or appropriate callbacks for this plugin.

    Shotgun credentials are retrieved from the `SGDAEMON_SGJIRA_NAME` and `SGDAEMON_SGJIRA_KEY`
    environment variables.

    :param reg: A Shotgun Event Daemon Registrar instance.
    """
    # Narrow down the list of events we pass to the bridge
    event_filter = {
        "Shotgun_Task_Change": ["*"],
        "Shotgun_Ticket_Change": ["*"],
        "Shotgun_Project_Change": ["*"],
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
    )

    # Set the logging level for this particular plugin. Let debug and above
    # messages through (don't block info, etc). This is particularly useful
    # for enabling and disabling debugging on a per plugin basis.
    reg.logger.setLevel(logging.DEBUG)


def process_event(sg, logger, event, dispatch_routes):
    """
    A callback which posts Jira sync requests.

    :param sg: Shotgun API handle.
    :param logger: Logger instance.
    :param event: A Shotgun EventLogEntry entity dictionary.
    :param dispatch_routes: A dictionary where keys are SG Project ids and values urls.
    """
    logger.debug("Processing %s" % event)

    # Sometimes rogue events from the site creation can be retrieved by the
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
        logger.debug(
            "Ignoring event %s not associated with any Project" % event
        )
        return

    # Shotgun requests are costly so we cache Projects dispatch routes and re-use
    # them when we treat an event for a Project we handled before.
    if project["id"] not in dispatch_routes:
        # This is the first time we treat an event for this Project, get the
        # routing, if any, from Shotgun
        logger.info("Retrieving sync routing for Project %d" % project["id"])
        sg_project = sg.find_one(
            "Project",
            [["id", "is", project["id"]]],
            ["name", "sg_jira_sync_url"]
        )
        if not sg_project:
            # This shouldn't happen, but better to be safe here.
            logger.warning(
                "Unable to retrieve a Shotgun Project "
                "with id %d, skipping event..." % (
                    project["id"]
                )
            )
            dispatch_routes[project["id"]] = None
            return
        # We expect a File/Link field with a web link, something like:
        # {
        #    'name': 'SG Jira Bridge',
        #    'url': 'http://localhost:9090',
        #    'content_type': None,
        #    'type': 'Attachment',
        #    'id': 123456,
        #    'link_type': 'web'
        #
        # }

        # Default value if we can't retrieve a valid value
        sync_url = None
        project_sync_value = sg_project.get("sg_jira_sync_url")
        if isinstance(project_sync_value, dict):
            if project_sync_value.get("link_type") == "web":
                sync_url = sg_project.get("sg_jira_sync_url").get("url")
                if sync_url and sync_url.endswith("/"):
                    sync_url = sync_url[:-1]
        dispatch_routes[sg_project["id"]] = sync_url

    sync_server_url = dispatch_routes[project["id"]]
    if not sync_server_url:
        logger.debug("Ignoring Jira sync for Project %d" % project["id"])
        return
    meta = event["meta"]
    entity_type = meta.get("entity_type")
    entity_id = meta.get("entity_id")
    if not entity_type or not entity_id:
        logger.debug("Ignoring event %s without valid Entity meta data.")
        return
    # Just send a POST request with the event meta data as payload.
    sync_url = "%s/%s/%d" % (sync_server_url, entity_type, entity_id)
    logger.debug("Posting event %s to %s" % (meta, sync_url))
    # Post application/json request
    payload = {
        "meta": meta,
        "session_uuid": event.get("session_uuid"),
        "user": event.get("user")
    }
    response = requests.post(
        sync_url,
        json=payload,
    )
    response.raise_for_status()
    logger.debug("Event successfully processed.")
