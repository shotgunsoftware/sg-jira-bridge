# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import sys

if sys.version_info[0] == 2:
    ex_type = ImportError
else:
    ex_type = ModuleNotFoundError

for module_name in ["daemonize", "shotgun_api3", "jira", "dotenv", "six"]:
    try:
        __import__(module_name)
    except ex_type as e:
        raise RuntimeError("Could not import '%s' module. Did you install the requirements.txt file? Original error: %s" % (module_name, str(e)))

from .bridge import Bridge
from .syncer import Syncer
from .jira_session import JiraSession
from .task_issue_syncer import TaskIssueSyncer
