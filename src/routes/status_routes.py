from datetime import datetime
from flask import Blueprint, jsonify
from src.planner.metrics import compute_metrics
import src.app as app_module

status_bp = Blueprint("status", __name__)


@status_bp.route("/api/status", methods=["GET"])
def get_status():
    storage = app_module.storage
    engine_info = storage.get_engine_info()
    plan = storage.get_plan() if engine_info["connected"] else None
    has_plan = plan is not None

    metrics = compute_metrics(plan) if has_plan else None

    return jsonify({
        "database": engine_info,
        "has_plan": has_plan,
        "is_paused": plan.get("is_paused", False) if plan else False,
        "paused_at": plan.get("paused_at") if plan else None,
        "metrics": metrics,
        "server_date": datetime.now().date().isoformat()
    })
