from src.logger import logger
from src.planner.rescheduler import update_plan_availability as reschedule_plan


def update_plan_availability(storage, weekly_availability, from_date_str=None, pace_multiplier=None):
    """
    Update plan's weekly availability and synchronize revision & completion bookmarks
    to MongoDB's problem_progress collection.
    """
    storage._ensure_connected()
    plan = storage.get_plan()
    if not plan:
        raise ValueError("No active plan to update.")

    progress_map = storage.get_problem_progress_map()
    updated_plan = reschedule_plan(
        plan,
        weekly_availability,
        from_date_str=from_date_str,
        pace_multiplier=pace_multiplier,
        existing_progress_map=progress_map
    )
    storage.save_plan(updated_plan)

    # Synchronize problem_progress collection with any revisions or completions
    try:
        for day in updated_plan.get("schedule", []):
            for p in day.get("problems", []):
                uid = p.get("uid")
                is_rev = bool(p.get("revision"))
                is_comp = bool(p.get("completed"))
                if is_rev or is_comp:
                    update_fields = {"problem_uid": uid}
                    if is_rev:
                        update_fields["revision"] = True
                        update_fields["revision_marked_at"] = p.get("revision_marked_at")
                    if is_comp:
                        update_fields["completed"] = True
                        update_fields["completed_at"] = p.get("completed_at")
                    storage.db.problem_progress.update_one(
                        {"problem_uid": uid},
                        {"$set": update_fields},
                        upsert=True
                    )
    except Exception as e:
        logger.error(f"Error syncing progress to collection: {e}")

    logger.info(f"Plan availability updated. Target completion: {updated_plan.get('target_completion_date')}")
    return updated_plan
