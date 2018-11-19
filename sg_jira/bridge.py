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
import fnmatch

import jira
from jira import JIRA, JIRAError
from shotgun_api3 import Shotgun

logger = logging.getLogger(__name__)
# Ensure basic logging is always enabled
logging.basicConfig(format="%(levelname)s:%(name)s:%(message)s")

class Bridge(object):
    """
    A brigde between Shotgun and Jira.
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
            # Check the status code, it is a string
            if e.status_code == 401:
                raise RuntimeError(
                    "Unable to connect to %s, please check your credentials" % (jira_site)
                )
            raise RuntimeError("Unable to connect to %s" % (jira_site))
        logger.info("Connected to %s..." % jira_site)
        self._sync_settings = sync_settings

    @classmethod
    def get_bridge(cls, settings_file):
        """
        Read the given settings and intantiate a new Bridge with them.
        """
        # Read settings
        settings = cls.read_settings(settings_file)

        # Set logging from settings
        logger_settings = getattr(settings, "LOGGING") or {}
        if logger_settings:
            logging.config.dictConfig(logger_settings)

        # Retrieve how to connect to Shotgun
        shotgun_settings = getattr(settings, "SHOTGUN") or {}
        if not shotgun_settings:
            raise ValueError("Missing Shotgun settings in %s" % settings_file)

        # Retrieve how to connect to Jira
        jira_settings = getattr(settings, "JIRA") or {}
        if not jira_settings:
            raise ValueError("Missing Jira settings in %s" % settings_file)

        sync_settings = getattr(settings, "SYNC") or {}
        if not sync_settings:
            raise ValueError("Missing sync settings in %s" % settings_file)

        logger.info("Successfully read settings from %s" % settings_file)
        try:
            return cls(
                shotgun_settings.get("site"),
                shotgun_settings.get("script_name"),
                shotgun_settings.get("script_key"),
                jira_settings.get("site"),
                jira_settings.get("user"),
                jira_settings.get("secret"),
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
        :returns: A Python module with the loaded settings.
        :raises: ValueError if the file does not exist or its name does not end
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
        return module

    def sync_in_jira(self, project_name, entity_type, entity_id):
        """
        Sync the given Shotgun Entity into Jira.
        """
        try:
            settings = self._get_settings_for_project(project_name)
        except Exception as e:
            # Catch the exception to log it and let it bubble up
            logger.exception(e)
            raise

    def sync_in_shotgun(self, project_name, resource_type, resource_id):
        """
        Sync the given Jira Resource into Shotgun.
        """
        try:
            settings = self._get_settings_for_project(project_name)
        except Exception as e:
            # Catch the exception to log it and let it bubble up
            logger.exception(e)
            raise

    def _get_settings_for_project(self, project_name):
        """
        Retrieve the setting for the given project_name.
        """
        # If we have the exact name in our keys, use it. Otherwise use the
        # first one which matches
        if project_name in self._sync_settings:
            logger.info("Using %s settings for %s" % (project_name, project_name))
            return self._sync_settings[project_name]
        for name in self._sync_settings:
            if fnmatch.fnmatch(project_name, name):
                logger.info("Using %s settings for %s" % (name, project_name))
                return self._sync_settings[name]
        return None
