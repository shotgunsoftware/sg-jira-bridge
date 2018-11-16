# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import imp
import inspect

import jira

class Bridge(object):
    """
    A brigde between Shotgun and Jira.
    """
    @classmethod
    def get_bridge(cls, settings_file):
        """
        Read the given settings and intantiate a new Bridge with them.
        """
        # Read settings
        settings = cls.read_settings(settings_file)
        return cls()

    @classmethod
    def read_settings(cls, settings_file):
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
            # Strip the extension if dealing with a .py
            os.path.splitext(name)[0],
            [folder]
        )
        module = imp.load_module(
            "%s.settings" % __name__,
            mfile,
            pathname,
            description
        )
        for setting in (s for s in dir(module) if not s.startswith('_')):
            setting_value = getattr(module, setting)
            if not inspect.ismodule(setting_value):
                result[setting] = setting_value

    def sync_in_jira(self, project_name, entity_type, entity_id):
        """
        Sync the given Shotgun Entity into Jira.
        """
        pass

    def sync_in_shotgun(self, project_name, resource_type, resource_id):
        """
        Sync the given Jira Resource into Shotgun.
        """
        pass
