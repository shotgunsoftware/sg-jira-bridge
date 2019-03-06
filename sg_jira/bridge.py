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
import importlib

from .shotgun_session import ShotgunSession
from .jira_session import JiraSession
from .constants import ALL_SETTINGS_KEYS
from .constants import LOGGING_SETTINGS_KEY, SYNC_SETTINGS_KEY
from .constants import SHOTGUN_SETTINGS_KEY, JIRA_SETTINGS_KEY
from .utils import utf8_to_unicode

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
        sg_http_proxy=None,
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
        :param str sg_http_proxy: Optional, a http proxy to use for the Shotgun
                                  connection, or None.
        """
        super(Bridge, self).__init__()
        self._shotgun = ShotgunSession(
            sg_site,
            script_name=sg_script,
            api_key=sg_script_key,
            http_proxy=sg_http_proxy,
        )
        self._shotgun.add_user_agent("sg_jira_sync")

        self._jira = JiraSession(
            jira_site,
            auth=(
                jira_user,
                jira_secret
            ),
        )
        logger.info("Connected to %s." % jira_site)
        self._sync_settings = sync_settings or {}
        self._syncers = {}
        self._jira.setup()
        self._shotgun.setup()

    @classmethod
    def get_bridge(cls, settings_file):
        """
        Read the given settings and instantiate a new :class:`Bridge` with them.

        :param str settings_file: Path to a settings Python file.
        :raises ValueError: on missing required settings.
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
                sg_http_proxy=shotgun_settings.get("http_proxy"),
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
        :raises ValueError: if the file does not exist or if its name does not end
                 with ``.py``.
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
    def shotgun(self):
        """
        Return a connected :class:`~shotgun_session.ShotgunSession` instance.
        """
        return self._shotgun

    @property
    def current_shotgun_user(self):
        """
        Return the Shotgun user used for the connection.

        :returns: A Shotgun record dictionary with an `id` key and a `type` key.
        """
        return self._shotgun.current_user

    @property
    def current_jira_username(self):
        """
        Return the username of the current Jira user.

        :returns: A string with the username.
        """
        return self.jira.current_user()

    @property
    def jira(self):
        """
        Return a connected :class:`~jira_session.JiraSession` instance.
        """
        return self._jira

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
        :raises ValueError: for invalid settings.
        """
        if name not in self._syncers:
            # Create the syncer from the settings
            sync_settings = self._sync_settings.get(name)
            if sync_settings is None:
                raise ValueError("Missing sync settings for %s" % name)
            if not isinstance(sync_settings, dict):
                raise ValueError(
                    "Invalid sync settings for %s, it must be dictionary." % name
                )
            # Retrieve the syncer
            syncer_name = sync_settings.get("syncer")
            if not syncer_name:
                raise ValueError("Missing `syncer` setting for %s" % name)
            if "." not in syncer_name:
                raise ValueError(
                    "Invalid `syncer` setting %s for %s: "
                    "it must be a <module path>.<class name>" % (
                        syncer_name,
                        name
                    )
                )
            module_name, class_name = syncer_name.rsplit(".", 1)
            module = importlib.import_module(module_name)
            try:
                syncer_class = getattr(module, class_name)
            except AttributeError as e:
                logger.debug("%s" % e, exc_info=True)
                raise ValueError(
                    "Unable to retrieve a %s class from module %s" % (
                        class_name,
                        module,
                    )
                )
            # Retrieve the settings for the syncer, if any
            settings = sync_settings.get("settings") or {}
            # Instantiate the syncer with our standard parameters and any
            # additional settings as parameters.
            self._syncers[name] = syncer_class(
                name=name,
                bridge=self,
                **settings
            )
            self._syncers[name].setup()
        return self._syncers[name]

    def sync_in_jira(self, settings_name, entity_type, entity_id, event, **kwargs):
        """
        Sync the given Shotgun Entity to Jira.

        :param str settings_name: The name of the settings to use for this sync.
        :param str entity_type: The Shotgun Entity type to sync.
        :param int entity_id: The id of the Shotgun Entity to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the Entity was actually synced in Jira, False if
                  syncing was skipped for any reason.
        """
        synced = False
        try:
            # Shotgun events might contain utf-8 encoded strings, convert them
            # to unicode before processing.
            safe_event = utf8_to_unicode(event)
            syncer = self.get_syncer(settings_name)
            # See comment in Syncer class: we assume copmlicated logic can be
            # handled in a single handler, so we don't have to support multiple
            # handlers.
            handler = syncer.accept_shotgun_event(entity_type, entity_id, safe_event)
            if handler:
                self._shotgun.set_session_uuid(safe_event.get("session_uuid"))
                synced = handler.process_shotgun_event(
                    entity_type,
                    entity_id,
                    safe_event
                )
        except Exception as e:
            # Catch the exception to log it and let it bubble up
            logger.exception(e)
            raise
        return synced

    def sync_in_shotgun(self, settings_name, resource_type, resource_id, event, **kwargs):
        """
        Sync the given Jira Resource to Shotgun.

        :param str settings_name: The name of the settings to use for this sync.
        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the resource was actually synced in Shotgun, False if
                  syncing was skipped for any reason.
        """
        synced = False
        try:
            syncer = self.get_syncer(settings_name)
            # See comment in Syncer class: we assume copmlicated logic can be
            # handled in a single handler, so we don't have to support multiple
            # handlers.
            handler = syncer.accept_jira_event(resource_type, resource_id, event)
            if handler:
                synced = handler.process_jira_event(resource_type, resource_id, event)
        except Exception as e:
            # Catch the exception to log it and let it bubble up
            logger.exception(e)
            raise
        return synced
