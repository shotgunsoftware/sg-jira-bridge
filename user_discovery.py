# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import sg_jira


parser = sg_jira.get_default_argument_parser()
parser.add_argument(
    "--project",
    type=str,
    help="The name of any Jira project that will be synced with Shotgun."
)
args = parser.parse_args()

bridge = sg_jira.Bridge.get_bridge(args.settings)
bridge.sync_jira_users_into_shotgun(args.project)