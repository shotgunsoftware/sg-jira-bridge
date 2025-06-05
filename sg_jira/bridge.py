# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import logging
import logging.config
import importlib
import importlib.util
import urllib
import threading

from .shotgun_session import ShotgunSession
from .jira_session import JiraSession
from .constants import ALL_SETTINGS_KEYS
from .constants import LOGGING_SETTINGS_KEY, SYNC_SETTINGS_KEY
from .constants import SHOTGUN_SETTINGS_KEY, JIRA_SETTINGS_KEY

logger = logging.getLogger(__name__)
# Ensure basic logging is always enabled
logging.basicConfig(format="%(levelname)s:%(name)s:%(message)s")


class Bridge(object):
    """
    A bridge between Flow Production Tracking and Jira.

    The bridge handles connections to the Flow Production Tracking and Jira servers and dispatches
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
        Instatiate a new bridge between the given PTR site and Jira site.

        .. note::
            Jira Cloud requires the use of an API token and will not work with
            a user's password. See https://confluence.atlassian.com/x/Vo71Nw
            for information on how to generate a token.
            Jira Server will use PAT so please provide empty string as `SGJIRA_JIRA_USER`.

        :param str sg_site: A Flow Production Tracking URL.
        :param str sg_script: A Flow Production Tracking script user name.
        :param str sg_script_key: The script user key for the Flow Production Tracking script.
        :param str jira_site: A Jira site url.
        :param str jira_user: A Jira user name, either his email address or short
                              name.
        :param str jira_secret: The Jira user password or API key.
        :param sync_settings: A dictionary where keys are settings names.
        :param str sg_http_proxy: Optional, a http proxy to use for the Flow Production Tracking
                                  connection, or None.
        """
        super().__init__()

        # The bridge webserver is multithreaded, which means we need to
        # track Shotgun connections via the API per thread. The PTR Python
        # API is not threadsafe, and using a single, global connection
        # across all threads will lead to some weird behavior.
        self._SG_CACHED_CONNECTIONS = threading.local()

        self._sg_site = sg_site
        self._sg_script = sg_script
        self._sg_script_key = sg_script_key
        self._sg_http_proxy = sg_http_proxy

        # Even though we will end up needing a connection per thread, we
        # still need to do a one-time check to make sure the site we're
        # connecting to is setup properly for use with the bridge. That
        # logic is run via the setup() method on the session object, so
        # we will connect here and call that a single time since there's
        # no reason to do that validation pass from each thread when we
        # create new connections.
        shotgun = ShotgunSession(
            sg_site,
            script_name=sg_script,
            api_key=sg_script_key,
            http_proxy=sg_http_proxy,
        )
        shotgun.add_user_agent("sg_jira_sync")
        shotgun.setup()

        self._jira_user = jira_user
        options = (
            {"token_auth": jira_secret}
            if jira_user in (None, "None", "")
            else {"basic_auth": (jira_user, jira_secret)}
        )
        self._jira = JiraSession(jira_site, **options)
        self._sync_settings = sync_settings or {}
        self._syncers = {}
        self._jira.setup()

    @classmethod
    def get_bridge(cls, settings_file):
        """
        Read the given settings and instantiate a new :class:`Bridge` with them.

        :param str settings_file: Path to a settings Python file.
        :raises ValueError: on missing required settings.
        """
        # make sure we have an absolute path
        settings_file_path = os.path.abspath(settings_file)

        # Read settings
        (
            logger_settings,
            shotgun_settings,
            jira_settings,
            sync_settings,
        ) = cls.read_settings(settings_file_path)

        if logger_settings:
            logging.config.dictConfig(logger_settings)

        logger.info("Successfully read settings from %s" % settings_file_path)
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
        :returns: A tuple of settings:
            (logger settings, shotgun settings, jira settings, sync settings)
        :raises ValueError: if the file does not exist or if its name does not end
                 with ``.py``.
        """
        full_path = os.path.abspath(settings_file)
        if not os.path.exists(settings_file):
            raise ValueError("Settings file %s does not exist" % full_path)
        if not full_path.endswith(".py"):
            raise ValueError(
                "Settings file %s is not a Python file with a .py extension" % full_path
            )

        _, module_name = os.path.split(full_path)
        module_name = os.path.splitext(module_name)[0]

        spec = importlib.util.spec_from_file_location(module_name, full_path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise ImportError(f"Could not import module {module_name}: {e}")
        
        # Retrieve all properties we handle and provide empty values if missing
        settings = dict(
            [
                (prop_name, getattr(module, prop_name, None))
                for prop_name in ALL_SETTINGS_KEYS
            ]
        )

        # Set logging from settings
        logger_settings = settings[LOGGING_SETTINGS_KEY]

        # Retrieve Shotgun connection settings
        shotgun_settings = settings[SHOTGUN_SETTINGS_KEY]
        if not shotgun_settings:
            raise ValueError("Missing Shotgun settings in %s" % full_path)
        missing = [
            name
            for name in ["site", "script_name", "script_key"]
            if not shotgun_settings.get(name)
        ]
        if missing:
            raise ValueError(
                "Missing Shotgun setting values %s in %s" % (missing, full_path)
            )

        # Retrieve Jira connection settings
        jira_settings = settings[JIRA_SETTINGS_KEY]
        if not jira_settings:
            raise ValueError("Missing Jira settings in %s" % full_path)

        missing = [name for name in ["site", "secret"] if not jira_settings.get(name)]
        if missing:
            raise ValueError(
                "Missing Jira setting values %s in %s" % (missing, full_path)
            )

        sync_settings = settings[SYNC_SETTINGS_KEY]
        if not sync_settings:
            raise ValueError("Missing sync settings in %s" % full_path)

        return logger_settings, shotgun_settings, jira_settings, sync_settings

    @property
    def shotgun(self):
        """
        Return a connected :class:`~shotgun_session.ShotgunSession` instance.
        """
        # This ensures we end up with a connection per thread. See the comment
        # at the top of this file where the global cache is initialized for a
        # full explanation.
        sg = getattr(self._SG_CACHED_CONNECTIONS, "sg", None)

        if sg is None:
            sg = ShotgunSession(
                self._sg_site,
                script_name=self._sg_script,
                api_key=self._sg_script_key,
                http_proxy=self._sg_http_proxy,
            )
            sg.add_user_agent("sg_jira_sync")
            self._SG_CACHED_CONNECTIONS.sg = sg

        return sg

    @property
    def current_shotgun_user(self):
        """
        Return the Flow Production Tracking user used for the connection.

        :returns: A Flow Production Tracking record dictionary with an `id` key and a `type` key.
        """
        return self.shotgun.current_user

    @property
    def current_jira_username(self):
        """
        Return the username of the current Jira user.

        The jira API escapes special characters using %xx syntax when storing
        the username. For example, the username ``richard+hendricks`` is stored
        as ``richard%2bhendricks`` by the jira API. We decode the username here
        before returning it to ensure we return the exact value (eg.
        ``richard+hendricks``)

        :returns: A string with the username.
        """
        return urllib.parse.unquote_plus(self.jira.current_user() or self._jira_user)

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
        return list(self._sync_settings.keys())

    def reset(self):
        """
        Reset the bridge.

        Clears all caches.
        """
        logger.debug("Resetting bridge")
        self.shotgun.clear_cached_field_schema()

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
                    "it must be a <module path>.<class name>" % (syncer_name, name)
                )
            module_name, class_name = syncer_name.rsplit(".", 1)
            module = importlib.import_module(module_name)
            try:
                syncer_class = getattr(module, class_name)
            except AttributeError as e:
                logger.debug("%s" % e, exc_info=True)
                raise ValueError(
                    "Unable to retrieve a %s class from module %s"
                    % (
                        class_name,
                        module,
                    )
                )
            # Retrieve the settings for the syncer, if any
            settings = sync_settings.get("settings") or {}
            # Instantiate the syncer with our standard parameters and any
            # additional settings as parameters.
            self._syncers[name] = syncer_class(name=name, bridge=self, **settings)
            self._syncers[name].setup()
        return self._syncers[name]

    def sync_in_jira(self, settings_name, entity_type, entity_id, event, **kwargs):
        """
        Sync the given Flow Production Tracking Entity to Jira.

        :param str settings_name: The name of the settings to use for this sync.
        :param str entity_type: The Flow Production Tracking Entity type to sync.
        :param int entity_id: The id of the Flow Production Tracking Entity to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the Entity was actually synced in Jira, False if
                  syncing was skipped for any reason.
        """
        synced = False
        try:
            syncer = self.get_syncer(settings_name)
            # See comment in Syncer class: we assume complicated logic can be
            # handled in a single handler, so we don't have to support multiple
            # handlers.
            handler = syncer.accept_shotgun_event(entity_type, entity_id, event)
            if handler:
                self.shotgun.set_session_uuid(event.get("session_uuid"))
                synced = handler.process_shotgun_event(entity_type, entity_id, event)
        except Exception as e:
            # Catch the exception to log it and let it bubble up
            logger.exception(e)
            raise
        return synced

    def sync_in_shotgun(
        self, settings_name, resource_type, resource_id, event, **kwargs
    ):
        """
        Sync the given Jira Resource to Flow Production Tracking.

        :param str settings_name: The name of the settings to use for this sync.
        :param str resource_type: The type of Jira resource sync, e.g. Issue.
        :param str resource_id: The id of the Jira resource to sync.
        :param event: A dictionary with the event meta data for the change.
        :returns: True if the resource was actually synced in Flow Production Tracking, False if
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
