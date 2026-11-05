import os
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from src.logger import logger
from src.storage import PlanlyMongoStorage
from src.planner import generate_plan, realign_or_resume_plan, compute_metrics, load_flattened_syllabus

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

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status", methods=["GET"])
def get_status():
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

@app.route("/api/plan", methods=["GET"])
def get_full_plan():
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

_CACHED_SYLLABUS = None

def get_cached_syllabus():
    global _CACHED_SYLLABUS
    if _CACHED_SYLLABUS is None:
        flat_problems, topics_summary = load_flattened_syllabus()
        _CACHED_SYLLABUS = (flat_problems, topics_summary)
    return _CACHED_SYLLABUS

@app.route("/api/syllabus", methods=["GET"])
def get_syllabus():
    try:
        flat_problems, topics_summary = get_cached_syllabus()
        return jsonify({
            "success": True,
            "topics_summary": topics_summary,
            "problems": flat_problems,
            "total_problems": len(flat_problems)
        })
    except Exception as e:
        logger.exception(f"Error fetching syllabus: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/create-plan", methods=["POST"])
def create_plan():
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
        new_plan = generate_plan(weekly_availability, start_date_str=start_date, pace_multiplier=pace_multiplier)
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

@app.route("/api/estimate-plan", methods=["POST"])
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
        est_weeks = round(estimated_plan["total_calendar_days"] / 7.0, 1)
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

@app.route("/api/today", methods=["GET"])
def get_today_tasks():
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

@app.route("/api/problem/<uid>/toggle", methods=["POST"])
def toggle_problem(uid):
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

@app.route("/api/problem/<uid>/revision", methods=["POST"])
@app.route("/api/problem/<uid>/toggle-revision", methods=["POST"])
def toggle_problem_revision(uid):
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

@app.route("/api/revisions", methods=["GET"])
def get_revisions():
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

@app.route("/api/day/<int:day_number>/toggle", methods=["POST"])
def toggle_day(day_number):
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

@app.route("/api/pause", methods=["POST"])
def pause_plan():
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

@app.route("/api/resume", methods=["POST"])
def resume_plan():
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

@app.route("/api/realign", methods=["POST"])
def realign_schedule():
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

@app.route("/api/reset-progress", methods=["POST"])
def reset_progress():
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

@app.route("/api/reset", methods=["POST"])
def reset_plan():
    try:
        storage.reset_plan()
        logger.info("Plan reset requested and completed.")
        return jsonify({"success": True, "message": "Plan cleared successfully."})
    except Exception as e:
        logger.exception(f"Error resetting plan: {e}")
        return jsonify({"error": str(e)}), 500

from src.config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG

def run_app():
    logger.info(f"Starting Planly DSA Scheduler on http://{FLASK_HOST}:{FLASK_PORT} (debug={FLASK_DEBUG})...")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)

if __name__ == "__main__":
    run_app()
