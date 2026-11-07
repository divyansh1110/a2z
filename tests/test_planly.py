"""
Comprehensive test suite for Planly DSA Scheduler.
Aggregates modular test suites for planner, storage, API, and logger.
"""

import unittest
from tests.test_logger import LoggerTestCase
from tests.test_planner import PlannerTestCase
from tests.test_storage import StorageTestCase
from tests.test_api import ApiTestCase

# Backward-compatible alias combining test cases for any tools expecting PlanlySrcTestCase
PlanlySrcTestCase = ApiTestCase


def suite():
    test_suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    test_suite.addTests(loader.loadTestsFromTestCase(LoggerTestCase))
    test_suite.addTests(loader.loadTestsFromTestCase(PlannerTestCase))
    test_suite.addTests(loader.loadTestsFromTestCase(StorageTestCase))
    test_suite.addTests(loader.loadTestsFromTestCase(ApiTestCase))
    return test_suite


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite())
