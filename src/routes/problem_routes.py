from datetime import datetime
from flask import Blueprint, request, jsonify
from src.logger import logger
from src.planner.metrics import compute_metrics
import src.app as app_module

problem_bp = Blueprint("problem", __name__)


@problem_bp.route("/api/today", methods=["GET"])
def get_today_tasks():
    storage = app_module.storage
    plan = storage.get_plan()
    if not plan:
        return jsonify({"has_plan": False, "database": storage.get_engine_info()}), 200

    date_str = request.args.get("date") or datetime.now().date().isoformat()
    metrics = compute_metrics(plan, current_date_str=date_str)

    return jsonify({
        "has_plan": True,
        "is_paused": plan.get("is_paused", False),
        "paused_at": plan.get("paused_at"),
        "today_date": date_str,
        "active_day": metrics.get("active_focus_day"),
        "metrics": metrics
    })


@problem_bp.route("/api/problem/<uid>/toggle", methods=["POST"])
def toggle_problem(uid):
    storage = app_module.storage
    plan = storage.get_plan()
    if not plan:
        return jsonify({"error": "No active plan found"}), 404

    data = request.get_json(silent=True) or {}
    forced_completed = data.get("completed")
    client_date = data.get("date") or request.args.get("date")

    if forced_completed is None:
        current_state = False
        for day in plan.get("schedule", []):
            if day.get("type") == "study":
                for p in day.get("problems", []):
                    if p.get("uid") == uid:
                        current_state = p.get("completed", False)
                        break
        target_state = not current_state
    else:
        target_state = bool(forced_completed)

    try:
        updated_plan, recalc_info = storage.update_problem_status(
            uid, target_state, current_date_str=client_date, return_meta=True
        )
        metrics = compute_metrics(updated_plan, current_date_str=client_date)
        return jsonify({
            "success": True,
            "uid": uid,
            "completed": target_state,
            "recalculated": recalc_info.get("recalculated", False),
            "moved_to_today": recalc_info.get("moved_to_today", False),
            "old_target_completion_date": recalc_info.get("old_target_date"),
            "new_target_completion_date": recalc_info.get("new_target_date"),
            "plan": updated_plan,
            "metrics": metrics
        })
    except Exception as e:
        logger.exception(f"Error toggling problem {uid}: {e}")
        return jsonify({"error": str(e)}), 500


@problem_bp.route("/api/problem/<uid>/revision", methods=["POST"])
@problem_bp.route("/api/problem/<uid>/toggle-revision", methods=["POST"])
def toggle_problem_revision(uid):
    storage = app_module.storage
    plan = storage.get_plan()
    if not plan:
        return jsonify({"error": "No active plan found"}), 404

    data = request.get_json(silent=True) or {}
    forced_revision = data.get("revision")

    if forced_revision is None:
        current_state = False
        for day in plan.get("schedule", []):
            if day.get("type") == "study":
                for p in day.get("problems", []):
                    if p.get("uid") == uid:
                        current_state = p.get("revision", False)
                        break
        target_state = not current_state
    else:
        target_state = bool(forced_revision)

    try:
        updated_plan = storage.update_problem_revision_status(uid, target_state)
        metrics = compute_metrics(updated_plan)
        return jsonify({
            "success": True,
            "uid": uid,
            "revision": target_state,
            "metrics": metrics
        })
    except Exception as e:
        logger.exception(f"Error updating revision for problem {uid}: {e}")
        return jsonify({"error": str(e)}), 500


@problem_bp.route("/api/revisions", methods=["GET"])
def get_revisions():
    storage = app_module.storage
    plan = storage.get_plan()
    if not plan:
        return jsonify({"success": True, "problems": [], "count": 0})

    revisions = []
    for day in plan.get("schedule", []):
        if day.get("type") == "study":
            for p in day.get("problems", []):
                if p.get("revision"):
                    prob_dict = dict(p)
                    prob_dict["day_number"] = day.get("day_number")
                    prob_dict["date"] = day.get("date")
                    revisions.append(prob_dict)

    return jsonify({
        "success": True,
        "problems": revisions,
        "count": len(revisions)
    })


@problem_bp.route("/api/day/<int:day_number>/toggle", methods=["POST"])
def toggle_day(day_number):
    storage = app_module.storage
    data = request.get_json() or {}
    completed = data.get("completed", True)

    try:
        updated_plan = storage.update_day_status(day_number, completed)
        if not updated_plan:
            return jsonify({"error": "Day or plan not found"}), 404

        metrics = compute_metrics(updated_plan)
        return jsonify({
            "success": True,
            "day_number": day_number,
            "completed": completed,
            "metrics": metrics
        })
    except Exception as e:
        logger.exception(f"Error toggling day {day_number}: {e}")
        return jsonify({"error": str(e)}), 500
