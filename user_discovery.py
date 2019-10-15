# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import sg_jira


bridge = sg_jira.Bridge.get_bridge("settings.py")
bridge.sync_jira_users_into_shotgun()