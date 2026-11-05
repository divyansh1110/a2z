"""
Entrypoint to run Planly DSA Scheduler
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.app import app
from src.logger import logger
from src.config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG

if __name__ == "__main__":
    logger.info(f"Planly starting on http://{FLASK_HOST}:{FLASK_PORT} (debug={FLASK_DEBUG}) ...")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
