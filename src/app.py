import os
from flask import Flask, request
from src.logger import logger
from src.storage import PlanlyMongoStorage
from src.routes import register_routes
from src.routes.syllabus_routes import get_cached_syllabus
from src.config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG

SRC_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(SRC_DIR, "templates"),
    static_folder=os.path.join(SRC_DIR, "static")
)

storage = PlanlyMongoStorage()

@app.before_request
def log_request_info():
    if request.path.startswith("/api"):
        logger.info(f"API Request: {request.method} {request.path}")

# Register modular route blueprints
register_routes(app)


def run_app():
    """Start Planly DSA Scheduler Flask server."""
    logger.info(f"Starting Planly DSA Scheduler on http://{FLASK_HOST}:{FLASK_PORT} (debug={FLASK_DEBUG})...")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)


if __name__ == "__main__":
    run_app()
