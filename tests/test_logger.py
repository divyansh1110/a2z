import os
import unittest
from src.logger import LOG_FILE


class LoggerTestCase(unittest.TestCase):
    def test_logger_file_created(self):
        # Verify logs directory and log file exist
        self.assertTrue(os.path.exists(LOG_FILE))
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("[planly]", content)


if __name__ == "__main__":
    unittest.main()
