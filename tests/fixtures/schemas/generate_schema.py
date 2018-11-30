# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

DESCRIPTION = """
A script to generate Shotgun schema for Mockgun.
"""
import argparse
import os

from shotgun_api3 import Shotgun
from shotgun_api3.lib import mockgun

def main():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION
    )
    parser.add_argument(
        "--path",
        help="Output directory path for schema files.",
        required=True,
    )
    parser.add_argument(
        "--shotgun",
        nargs=3,
        help="A SG site url, a script name and its key",
        required=True,
    )
    args = parser.parse_args()

    sg_url, sg_script, sg_key = args.shotgun
    sg = Shotgun(sg_url, sg_script, sg_key)
    schema_dir = args.path
    if not os.path.exists(schema_dir):
        os.makedirs(schema_dir)
    mockgun.generate_schema(
        sg,
        os.path.join(schema_dir, "schema.pickle"),
        os.path.join(schema_dir, "schema_entity.pickle")
    )

if __name__ == "__main__":
    main()
