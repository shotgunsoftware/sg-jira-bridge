# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import os
import sys
import tempfile
import time
import unittest
from multiprocessing import Process

if not sys.platform.startswith("win"):
    import service


@unittest.skipIf(sys.platform.startswith("win"), "Requires Linux/Osx")
class TestService(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._fixtures_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "fixtures")
        )

    def test_service_status(self):
        """
        Test querying the web app service is resilient.
        """
        with tempfile.NamedTemporaryFile() as pid_f:
            # Check that an empty pid file does not cause problems
            service.status(pid_f.name)
            # Check that bad values in the pid file do not cause problems
            pid_f.write(b"badpid")
            pid_f.flush()
            service.status(pid_f.name)

    @unittest.skipUnless(
        os.environ.get("SGJIRA_SG_SITE")
        and os.environ.get("SGJIRA_SG_SCRIPT_NAME")
        and os.environ.get("SGJIRA_SG_SCRIPT_KEY")
        and os.environ.get("SGJIRA_JIRA_SITE")
        and os.environ.get("SGJIRA_JIRA_USER")
        and os.environ.get("SGJIRA_JIRA_USER_SECRET"),
        "Requires SGJIRA_SG_SITE, SGJIRA_SG_SCRIPT_NAME, SGJIRA_SG_SCRIPT_KEY, "
        "SGJIRA_JIRA_SITE, SGJIRA_JIRA_USER, SGJIRA_JIRA_USER_SECRET env vars.",
    )
    def test_service_start_stop(self):
        """
        Test we can start stop and query the web app service
        """
        # Stopping the service will unlink the pid file
        with tempfile.NamedTemporaryFile(delete=False) as pid_f:
            process = Process(
                target=service.start,
                args=(
                    pid_f.name,
                    9090,
                    "localhost",
                    os.path.join(self._fixtures_path, "settings.py"),
                ),
            )
            process.start()
            self.assertIsNotNone(process.pid)
            process.join(1)
            # Make sure the daemon has the time to start and store its pid in
            # the pid file.
            time.sleep(1)
            try:
                self.assertIsNotNone(service.status(pid_f.name))
                service.stop(pid_f.name)
                self.assertIsNone(service.status(pid_f.name))
                self.assertFalse(os.path.exists(pid_f.name))
            except Exception:
                print("Process exit code {}".format(process.exitcode))
                raise
