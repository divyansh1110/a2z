"""
Routes package for Planly DSA Scheduler.
Registers blueprints for views, status, syllabus, study plans, and problem tracking.
"""

from src.routes.views import views_bp
from src.routes.status_routes import status_bp
from src.routes.syllabus_routes import syllabus_bp
from src.routes.plan_routes import plan_bp
from src.routes.problem_routes import problem_bp


def register_routes(app):
    """Register all application blueprints with the Flask app."""
    app.register_blueprint(views_bp)
    app.register_blueprint(status_bp)
    app.register_blueprint(syllabus_bp)
    app.register_blueprint(plan_bp)
    app.register_blueprint(problem_bp)
