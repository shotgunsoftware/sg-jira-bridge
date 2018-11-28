# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import imp
import logging
import logging.config

# import jira
from jira import JIRA, JIRAError
from shotgun_api3 import Shotgun

from .constants import ALL_SETTINGS_KEYS
from .constants import LOGGING_SETTINGS_KEY, SYNC_SETTINGS_KEY
from .constants import SHOTGUN_SETTINGS_KEY, JIRA_SETTINGS_KEY
from .syncer import Syncer

logger = logging.getLogger(__name__)
# Ensure basic logging is always enabled
logging.basicConfig(format="%(levelname)s:%(name)s:%(message)s")


class Bridge(object):
    """
    A bridge between Shotgun and Jira.

    The bridge handles connections to the Shotgun and Jira servers and dispatches
    sync events.
    """
    def __init__(
        self,
        sg_site,
        sg_script,
        sg_script_key,
        jira_site,
        jira_user,
        jira_secret,
        sync_settings=None,
    ):
        """
        Instatiate a new bridge between the given SG site and Jira site.

        :param str sg_site: A Shotgun site url.
        :param str sg_script: A Shotgun script user name.
        :param str sg_script_key: The script user key for the Shotgun script.
        :param str jira_site: A Jira site url.
        :param str jira_user: A Jira user name, either his email address or short
                              name.
        :param str jira_secret: The Jira user password.
        :param sync_settings: A dictionary where keys are settings names.
        """
        super(Bridge, self).__init__()
        self._shotgun = Shotgun(
            sg_site,
            script_name=sg_script,
            api_key=sg_script_key,
        )
        logger.info("Connected to %s..." % sg_site)
        try:
            self._jira = JIRA(
                jira_site,
                basic_auth=(
                    jira_user,
                    jira_secret
                ),
            )
        except JIRAError as e:
            # Jira puts some huge html / java script code in the exception
            # string so we catch it to issue a more reasonable message.
            logger.debug(
                "Unable to connect to %s: %s" % (jira_site, e),
                exc_info=True
            )
            # Check the status code
            if e.status_code == 401:
                raise RuntimeError(
                    "Unable to connect to %s, "
                    "please check your credentials" % jira_site
                )
            raise RuntimeError("Unable to connect to %s" % jira_site)
        logger.info("Connected to %s..." % jira_site)
        self._sync_settings = sync_settings or {}
        self._syncers = {}

    @classmethod
    def get_bridge(cls, settings_file):
        """
        Read the given settings and instantiate a new :class:`Bridge` with them.

        :param str settings_file: Path to a settings Python file.
        :raises: ValueError on missing required settings.
        """
        # Read settings
        settings = cls.read_settings(settings_file)

        # Set logging from settings
        logger_settings = settings[LOGGING_SETTINGS_KEY]
        if logger_settings:
            logging.config.dictConfig(logger_settings)

        # Retrieve Shotgun connection settings
        shotgun_settings = settings[SHOTGUN_SETTINGS_KEY]
        if not shotgun_settings:
            raise ValueError("Missing Shotgun settings in %s" % settings_file)
        missing = [
            name for name in ["site", "script_name", "script_key"] if not shotgun_settings.get(name)
        ]
        if missing:
            raise ValueError(
                "Missing Shotgun setting values %s in %s" % (missing, settings_file)
            )

        # Retrieve Jira connection settings
        jira_settings = settings[JIRA_SETTINGS_KEY]
        if not jira_settings:
            raise ValueError("Missing Jira settings in %s" % settings_file)

        missing = [
            name for name in ["site", "user", "secret"] if not jira_settings.get(name)
        ]
        if missing:
            raise ValueError(
                "Missing Jira setting values %s in %s" % (missing, settings_file)
            )

        sync_settings = settings[SYNC_SETTINGS_KEY]
        if not sync_settings:
            raise ValueError("Missing sync settings in %s" % settings_file)

        logger.info("Successfully read settings from %s" % settings_file)
        try:
            return cls(
                shotgun_settings["site"],
                shotgun_settings["script_name"],
                shotgun_settings["script_key"],
                jira_settings["site"],
                jira_settings["user"],
                jira_settings["secret"],
                sync_settings,
            )
        except Exception as e:
            logger.exception(e)
            raise

    @classmethod
    def read_settings(cls, settings_file):
        """
        Read the given settings file.

        :param str settings_file: Path to a settings Python file.
        :returns: A dictionary with the settings.
        :raises: ValueError if the file does not exist or if its name does not end
                 with .py.
        """
        result = {}
        full_path = os.path.abspath(settings_file)
        if not os.path.exists(settings_file):
            raise ValueError("Settings file %s does not exist" % full_path)
        if not full_path.endswith(".py"):
            raise ValueError(
                "Settings file %s is not a Python file with a .py extension" % full_path
            )

        folder, name = os.path.split(full_path)

        mfile, pathname, description = imp.find_module(
            # Strip the .py extension
            os.path.splitext(name)[0],
            [folder]
        )
        try:
            module = imp.load_module(
                "%s.settings" % __name__,
                mfile,
                pathname,
                description
            )
        finally:
            if mfile:
                mfile.close()
        # Retrieve all properties we handle and provide empty values if missing
        result = dict(
            [(prop_name, getattr(module, prop_name, None)) for prop_name in ALL_SETTINGS_KEYS]
        )
        return result

    @property
    def sync_settings_names(self):
        """
        Return the list of sync settings this bridge handles.
        """
        return self._sync_settings.keys()

    def get_syncer(self, name):
        """
        Returns a :class:`Syncer` instance for the given settings name.

        :param str: A settings name.
        :raises: ValueError for invalid settings name.
        """
        if name not in self._syncers:
            # Create the syncer from the settings
            if name not in self._sync_settings:
                raise ValueError("Unknown sync settings %s" % name)
            # Retrieve the syncer
            self._syncers[name] = Syncer(
                name,
                self._shotgun,
                self._jira,
                **self._sync_settings[name]
            )

        return self._syncers[name]

    def sync_in_jira(self, settings_name, entity_type, entity_id, event, **kwargs):
        """
        Sync the given Shotgun Entity to Jira.

        :param str settings_name: The name of the settings to use for this sync.
        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event meta data for the change.
        """
        try:
            syncer = self.get_syncer(settings_name)
            if syncer.accept_shotgun_event(entity_type, entity_id, event):
                syncer.process_shotgun_event(entity_type, entity_id, event)
        except Exception as e:
            # Catch the exception to log it and let it bubble up
            logger.exception(e)
            raise

    def sync_in_shotgun(self, settings_name, resource_type, resource_id, event, **kwargs):
        """
        Sync the given Jira Resource to Shotgun.

        :param str settings_name: The name of the settings to use for this sync.
        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        """
        try:
            syncer = self.get_syncer(settings_name)
            if syncer.accept_jira_event(resource_type, resource_id, event):
                syncer.process_jira_event(resource_type, resource_id, event)
        except Exception as e:
            # Catch the exception to log it and let it bubble up
            logger.exception(e)
            raise
