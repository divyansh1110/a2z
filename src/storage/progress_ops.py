from datetime import datetime
from src.logger import logger
from src.planner.recalculator import recalculate_future_schedule
from src.planner.generator import generate_plan


def get_problem_progress_map(db):
    """Retrieve all recorded problem progress and revision statuses from MongoDB."""
    if db is None:
        return {}
    try:
        cursor = db.problem_progress.find({}, {"_id": 0})
        res = {}
        for doc in cursor:
            if isinstance(doc, dict) and "problem_uid" in doc:
                res[doc["problem_uid"]] = doc
        return res
    except Exception as e:
        logger.error(f"Error reading problem_progress: {e}")
        return {}


def update_problem_status(storage, problem_uid, completed, completed_at=None, current_date_str=None, return_meta=False):
    """Update completion status of a problem, dynamically recalculating future schedule if completed ahead of time."""
    storage._ensure_connected()

    if completed and not completed_at:
        completed_at = datetime.now().isoformat()
    elif not completed:
        completed_at = None

    # 1. Update problem_progress collection
    try:
        storage.db.problem_progress.update_one(
            {"problem_uid": problem_uid},
            {"$set": {"problem_uid": problem_uid, "completed": bool(completed), "completed_at": completed_at}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error updating problem_progress collection: {e}")

    # 2. Update embedded plan document
    plan = storage.get_plan()
    if not plan:
        recalc_meta = {
            "recalculated": False,
            "moved_to_today": False,
            "old_target_date": None,
            "new_target_date": None
        }
        return (None, recalc_meta) if return_meta else None

    schedule = plan.get("schedule", [])
    old_target_date = plan.get("target_completion_date")

    # If completed == False (unchecking): keep in-place without schedule recalculation
    if not completed:
        found = False
        for day in schedule:
            if day.get("type") != "study":
                continue
            for prob in day.get("problems", []):
                if prob.get("uid") == problem_uid:
                    prob["completed"] = False
                    prob["completed_at"] = None
                    found = True
                    break
            if found:
                day["completed"] = all(p.get("completed", False) for p in day.get("problems", []))
                break

        if found:
            storage.save_plan(plan)
            logger.info(f"Problem {problem_uid} marked incomplete in-place")

        recalc_meta = {
            "recalculated": False,
            "moved_to_today": False,
            "old_target_date": old_target_date,
            "new_target_date": plan.get("target_completion_date")
        }
        return (plan, recalc_meta) if return_meta else plan

    # If completed == True: check if problem belongs to a future day and needs dynamic recalculation
    updated_plan, was_recalc, was_moved, old_t, new_t = recalculate_future_schedule(
        plan, today_date_str=current_date_str, problem_completed_uid=problem_uid
    )

    if was_recalc and was_moved:
        storage.save_plan(updated_plan)
        logger.info(
            f"Problem {problem_uid} completed ahead of schedule -> Moved to Today & recalculated schedule. "
            f"Target date changed: {old_t} -> {new_t}"
        )
        recalc_meta = {
            "recalculated": True,
            "moved_to_today": True,
            "old_target_date": old_t,
            "new_target_date": new_t
        }
        return (updated_plan, recalc_meta) if return_meta else updated_plan

    # If not a future day (e.g. today or past backlog day): update in-place
    found = False
    for day in schedule:
        if day.get("type") != "study":
            continue
        for prob in day.get("problems", []):
            if prob.get("uid") == problem_uid:
                prob["completed"] = True
                prob["completed_at"] = completed_at
                found = True
                break
        if found:
            day["completed"] = all(p.get("completed", False) for p in day.get("problems", []))
            break

    if found:
        storage.save_plan(plan)
        logger.info(f"Problem {problem_uid} updated -> completed=True")

    recalc_meta = {
        "recalculated": False,
        "moved_to_today": False,
        "old_target_date": old_target_date,
        "new_target_date": plan.get("target_completion_date")
    }
    return (plan, recalc_meta) if return_meta else plan


def update_problem_revision_status(storage, problem_uid, revision, revision_marked_at=None):
    """Toggle revision bookmark on a problem, synchronizing both collection and embedded plan."""
    storage._ensure_connected()

    if revision and not revision_marked_at:
        revision_marked_at = datetime.now().isoformat()
    elif not revision:
        revision_marked_at = None

    # 1. Update problem_progress collection in Mongo
    try:
        storage.db.problem_progress.update_one(
            {"problem_uid": problem_uid},
            {"$set": {"problem_uid": problem_uid, "revision": bool(revision), "revision_marked_at": revision_marked_at}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error updating problem revision in problem_progress collection: {e}")

    # 2. Update embedded plan document
    plan = storage.get_plan()
    if not plan:
        return None

    found = False
    for day in plan.get("schedule", []):
        if day.get("type") != "study":
            continue
        for prob in day.get("problems", []):
            if prob.get("uid") == problem_uid:
                prob["revision"] = bool(revision)
                prob["revision_marked_at"] = revision_marked_at
                found = True
                break
        if found:
            break

    if found:
        storage.save_plan(plan)
        logger.info(f"Problem {problem_uid} updated -> revision={revision}")

    return plan


def update_day_status(storage, day_number, completed):
    """Mark all problems in a given study day completed or incomplete."""
    storage._ensure_connected()
    plan = storage.get_plan()
    if not plan:
        return None

    now_str = datetime.now().isoformat() if completed else None
    target_day = None

    for day in plan.get("schedule", []):
        if day.get("type") == "study" and day.get("day_number") == day_number:
            target_day = day
            day["completed"] = bool(completed)
            for prob in day.get("problems", []):
                prob["completed"] = bool(completed)
                prob["completed_at"] = now_str
                try:
                    storage.db.problem_progress.update_one(
                        {"problem_uid": prob["uid"]},
                        {"$set": {"problem_uid": prob["uid"], "completed": bool(completed), "completed_at": now_str}},
                        upsert=True
                    )
                except Exception as e:
                    logger.error(f"Error updating progress in mongo for {prob.get('uid')}: {e}")
            break

    if target_day:
        storage.save_plan(plan)
        logger.info(f"Study Day {day_number} updated -> completed={completed}")

    return plan


def set_pause(storage, is_paused, paused_at=None):
    """Set the pause state on the active plan."""
    storage._ensure_connected()
    plan = storage.get_plan()
    if not plan:
        return None

    plan["is_paused"] = bool(is_paused)
    if is_paused:
        plan["paused_at"] = paused_at or datetime.now().isoformat()
        logger.info(f"Study plan paused at {plan['paused_at']}")
    else:
        plan["paused_at"] = None
        logger.info("Study plan resumed from pause")

    storage.save_plan(plan)
    return plan


def reset_progress(storage, restart_schedule=True, start_date_str=None):
    """Reset problem completion progress to 0% while strictly preserving revision bookmarks."""
    storage._ensure_connected()
    plan = storage.get_plan()
    if not plan:
        return None

    # 1. Clear individual problem progress from MongoDB collection, BUT PRESERVE REVISION QUESTIONS!
    try:
        # Delete progress records that are NOT marked for revision
        storage.db.problem_progress.delete_many({"revision": {"$ne": True}})
        # For records that ARE marked for revision, reset completed to False
        storage.db.problem_progress.update_many({"revision": True}, {"$set": {"completed": False, "completed_at": None}})
        logger.info("Cleared problem completion progress in MongoDB while strictly preserving revision marks.")
    except Exception as e:
        logger.error(f"Error resetting problem_progress in MongoDB: {e}")

    # 2. Reset plan schedule & problems
    if restart_schedule:
        target_start = start_date_str or datetime.now().date().isoformat()
        weekly_avail = plan.get("weekly_availability", {})
        pace_multiplier = plan.get("pace_multiplier", 1.0)
        progress_map = storage.get_problem_progress_map()
        new_plan = generate_plan(
            weekly_avail,
            start_date_str=target_start,
            pace_multiplier=pace_multiplier,
            existing_progress_map=progress_map
        )
        storage.save_plan(new_plan)
        logger.info(f"Progress reset to 0 with rescheduled plan starting {target_start} (revisions preserved)")
        return new_plan
    else:
        # Retain existing calendar schedule dates, reset all problem completion statuses but preserve revision
        for day in plan.get("schedule", []):
            day["completed"] = False
            for prob in day.get("problems", []):
                prob["completed"] = False
                prob["completed_at"] = None
        plan["is_paused"] = False
        plan["paused_at"] = None
        storage.save_plan(plan)
        logger.info("Progress reset to 0 retaining original calendar schedule dates and revision marks.")
        return plan
