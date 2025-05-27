# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import sys


ex_type = ModuleNotFoundError

IMPORT_MODULES = ["shotgun_api3", "jira", "dotenv"]

if sys.platform != "win32":
    IMPORT_MODULES.append("daemonize")

for module_name in IMPORT_MODULES:
    try:
        __import__(module_name)
    except ex_type as e:
        raise RuntimeError(
            "Could not import '%s' module. Did you install the requirements.txt file? Original error: %s"
            % (module_name, str(e))
        )

from .bridge import Bridge
from .syncer import Syncer
from .jira_session import JiraSession
from .task_issue_syncer import TaskIssueSyncer
