# Copyright 2018 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import sys
import os
import argparse
import unittest2 as unittest
import xmlrunner

import logging
logging.basicConfig(format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("run_tests")
logger.setLevel(logging.INFO)


class TestRunner(object):
    """
    A test runner which auto discovers all tests and supports xml output.
    """
    def __init__(self, xml_output=None):
        """
        :param xml_output: Directory path where xml reports are generated.
        """
        self.suite = None
        self._xml_output = xml_output
        # Tweak Python path so our modules can be found
        sys.path.insert(
            0,
            os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        )
        sys.path.insert(
            0,
            os.path.abspath(os.path.join(os.path.dirname(__file__), "python"))
        )

    def setup_suite(self, test_names):
        """
        Setup the test suite.

        :param test_names: Optional list of `module.TestCase.test1` to consider.
        """
        # args used to specify specific module.TestCase.test
        if test_names:
            self.suite = unittest.loader.TestLoader().loadTestsFromNames(test_names)
        else:
            self.suite = unittest.loader.TestLoader().discover(
                os.path.dirname(os.path.abspath(__file__))
            )

    def run_tests(self, test_names):
        """
        Run the given tests or all tests.

        :param test_names: Optional list of `module.TestCase.test1` to consider.
        """
        self.setup_suite(test_names)
        if self._xml_output:
            return xmlrunner.XMLTestRunner(output=self._xml_output).run(self.suite)
        else:
            return unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(self.suite)


def run_tests():
    """
    Parse command line parameters and run the tests.

    :returns: A :class:`unittest.TestResult` instance.
    """
    parser = argparse.ArgumentParser(
        description="run tests"
    )
    parser.add_argument(
        "--xmlout",
        help="Output directory for xml reports",
    )
    # Dump the environment for debug purpose
    for name, value in os.environ.iteritems():
        logger.info("Env %s: %s" % (name, value))
    args, other_args = parser.parse_known_args()
    runner = TestRunner(args.xmlout)
    return runner.run_tests(other_args)


if __name__ == "__main__":
    # Exit value determined by failures and errors
    exit_val = 0
    ret_val = run_tests()
    if ret_val.errors or ret_val.failures:
        exit_val = 1
    exit(exit_val)
