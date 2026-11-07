from datetime import datetime
from flask import Blueprint, request, jsonify
from src.logger import logger
from src.planner.generator import generate_plan
from src.planner.rescheduler import realign_or_resume_plan
from src.planner.metrics import compute_metrics
import src.app as app_module

plan_bp = Blueprint("plan", __name__)


@plan_bp.route("/api/plan", methods=["GET"])
def get_full_plan():
    storage = app_module.storage
    engine_info = storage.get_engine_info()
    if not engine_info["connected"]:
        return jsonify({
            "has_plan": False,
            "database": engine_info,
            "plan": None,
            "error": "MongoDB is not reachable at localhost:27017. Please start mongod."
        }), 200

    plan = storage.get_plan()
    if not plan:
        return jsonify({"has_plan": False, "database": engine_info, "plan": None}), 200

    metrics = compute_metrics(plan)
    return jsonify({
        "has_plan": True,
        "database": engine_info,
        "plan": plan,
        "metrics": metrics
    })


@plan_bp.route("/api/create-plan", methods=["POST"])
def create_plan():
    storage = app_module.storage
    engine_info = storage.get_engine_info()
    if not engine_info["connected"]:
        logger.error("Cannot create plan: MongoDB is not connected.")
        return jsonify({
            "error": "MongoDB is not running on localhost:27017. Please start the MongoDB service (mongod)."
        }), 503

    data = request.get_json() or {}
    weekly_availability = data.get("weekly_availability")
    if not weekly_availability:
        return jsonify({"error": "weekly_availability is required"}), 400

    start_date = data.get("start_date") or datetime.now().date().isoformat()
    pace_multiplier = float(data.get("pace_multiplier", 1.0))

    try:
        progress_map = storage.get_problem_progress_map()
        if not isinstance(progress_map, dict):
            progress_map = {}

        new_plan = generate_plan(
            weekly_availability,
            start_date_str=start_date,
            pace_multiplier=pace_multiplier,
            existing_progress_map=progress_map
        )
        storage.save_plan(new_plan)
        metrics = compute_metrics(new_plan)
        logger.info(f"Plan created successfully starting {start_date}")
        return jsonify({
            "success": True,
            "message": "Study plan created successfully!",
            "plan": new_plan,
            "metrics": metrics
        })
    except Exception as e:
        logger.exception(f"Error creating study plan: {e}")
        return jsonify({"error": str(e)}), 400


@plan_bp.route("/api/update-plan", methods=["POST"])
@plan_bp.route("/api/edit-plan", methods=["POST"])
def update_plan():
    storage = app_module.storage
    engine_info = storage.get_engine_info()
    if not engine_info["connected"]:
        return jsonify({
            "error": "MongoDB is not running on localhost:27017. Please start the MongoDB service (mongod)."
        }), 503

    plan = storage.get_plan()
    if not plan:
        return jsonify({"error": "No active plan found to update. Please create a plan first."}), 404

    data = request.get_json() or {}
    weekly_availability = data.get("weekly_availability")
    if not weekly_availability:
        return jsonify({"error": "weekly_availability is required"}), 400

    from_date = data.get("from_date")
    pace_multiplier = data.get("pace_multiplier")
    if pace_multiplier is not None:
        try:
            pace_multiplier = float(pace_multiplier)
        except (ValueError, TypeError):
            pace_multiplier = None

    try:
        updated_plan = storage.update_plan_availability(
            weekly_availability,
            from_date_str=from_date,
            pace_multiplier=pace_multiplier
        )
        metrics = compute_metrics(updated_plan)
        logger.info(f"Study plan availability updated successfully (from_date={from_date}).")
        return jsonify({
            "success": True,
            "message": "Study plan updated successfully! Progress and revision questions preserved.",
            "plan": updated_plan,
            "metrics": metrics
        })
    except Exception as e:
        logger.exception(f"Error updating study plan: {e}")
        return jsonify({"error": str(e)}), 400


@plan_bp.route("/api/estimate-plan", methods=["POST"])
def estimate_plan():
    data = request.get_json() or {}
    weekly_availability = data.get("weekly_availability")
    if not weekly_availability:
        return jsonify({"error": "weekly_availability is required"}), 400

    start_date = data.get("start_date") or datetime.now().date().isoformat()
    pace_multiplier = float(data.get("pace_multiplier", 1.0))

    try:
        norm_avail = {
            d: max(0.0, float(weekly_availability.get(d, 0.0)))
            for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        }
        if sum(norm_avail.values()) <= 0:
            return jsonify({
                "valid": False,
                "message": "Select at least 1 day with hours > 0"
            }), 200

        estimated_plan = generate_plan(norm_avail, start_date_str=start_date, pace_multiplier=pace_multiplier)
        est_weeks = estimated_plan.get("total_weeks") or round(estimated_plan["total_calendar_days"] / 7.0, 1)
        return jsonify({
            "valid": True,
            "start_date": start_date,
            "target_completion_date": estimated_plan["target_completion_date"],
            "total_study_days": estimated_plan["total_study_days"],
            "total_rest_days": estimated_plan["total_rest_days"],
            "total_calendar_days": estimated_plan["total_calendar_days"],
            "est_weeks": est_weeks
        })
    except Exception as e:
        logger.exception(f"Error estimating study plan: {e}")
        return jsonify({"error": str(e)}), 400


@plan_bp.route("/api/pause", methods=["POST"])
def pause_plan():
    storage = app_module.storage
    try:
        updated_plan = storage.set_pause(True)
        if not updated_plan:
            return jsonify({"error": "No plan to pause"}), 404

        metrics = compute_metrics(updated_plan)
        return jsonify({
            "success": True,
            "is_paused": True,
            "message": "Plan paused successfully. Take a well-deserved break!",
            "metrics": metrics
        })
    except Exception as e:
        logger.exception(f"Error pausing plan: {e}")
        return jsonify({"error": str(e)}), 500


@plan_bp.route("/api/resume", methods=["POST"])
def resume_plan():
    storage = app_module.storage
    plan = storage.get_plan()
    if not plan:
        return jsonify({"error": "No plan to resume"}), 404

    data = request.get_json() or {}
    resume_date = data.get("resume_date") or datetime.now().date().isoformat()
    updated_avail = data.get("weekly_availability")

    try:
        updated_plan = realign_or_resume_plan(plan, resume_date_str=resume_date, updated_availability=updated_avail)
        storage.save_plan(updated_plan)
        metrics = compute_metrics(updated_plan)
        logger.info(f"Plan resumed from {resume_date}")
        return jsonify({
            "success": True,
            "message": "Plan resumed! Remaining schedule has been updated.",
            "plan": updated_plan,
            "metrics": metrics
        })
    except Exception as e:
        logger.exception(f"Error resuming plan: {e}")
        return jsonify({"error": str(e)}), 400


@plan_bp.route("/api/realign", methods=["POST"])
def realign_schedule():
    storage = app_module.storage
    plan = storage.get_plan()
    if not plan:
        return jsonify({"error": "No active plan to realign"}), 404

    data = request.get_json() or {}
    from_date = data.get("from_date") or datetime.now().date().isoformat()
    updated_avail = data.get("weekly_availability")

    try:
        updated_plan = realign_or_resume_plan(plan, resume_date_str=from_date, updated_availability=updated_avail)
        storage.save_plan(updated_plan)
        metrics = compute_metrics(updated_plan)
        logger.info(f"Plan realigned from {from_date}")
        return jsonify({
            "success": True,
            "message": "Schedule re-aligned successfully from " + from_date,
            "plan": updated_plan,
            "metrics": metrics
        })
    except Exception as e:
        logger.exception(f"Error realigning schedule: {e}")
        return jsonify({"error": str(e)}), 400


@plan_bp.route("/api/reset-progress", methods=["POST"])
def reset_progress():
    storage = app_module.storage
    plan = storage.get_plan()
    if not plan:
        return jsonify({"error": "No active plan found to reset progress"}), 404

    data = request.get_json() or {}
    restart_schedule = bool(data.get("restart_schedule", True))
    start_date = data.get("start_date") or datetime.now().date().isoformat()

    try:
        updated_plan = storage.reset_progress(restart_schedule=restart_schedule, start_date_str=start_date)
        if not updated_plan:
            return jsonify({"error": "Failed to reset progress"}), 500

        metrics = compute_metrics(updated_plan)
        logger.info(f"Plan progress reset to 0 (restart_schedule={restart_schedule}, start_date={start_date})")
        return jsonify({
            "success": True,
            "message": "Progress reset to 0 successfully! Ready to start fresh.",
            "plan": updated_plan,
            "metrics": metrics
        })
    except Exception as e:
        logger.exception(f"Error resetting plan progress: {e}")
        return jsonify({"error": str(e)}), 400


@plan_bp.route("/api/reset", methods=["POST"])
def reset_plan():
    storage = app_module.storage
    try:
        storage.reset_plan()
        logger.info("Plan reset requested and completed.")
        return jsonify({"success": True, "message": "Plan cleared successfully."})
    except Exception as e:
        logger.exception(f"Error resetting plan: {e}")
        return jsonify({"error": str(e)}), 500
