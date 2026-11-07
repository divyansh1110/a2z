from datetime import datetime
from src.logger import logger
from src.planner.calendar_utils import compute_week_number


def save_plan_doc(db, plan_data):
    """Save or update the active study plan in MongoDB."""
    now_str = datetime.now().isoformat()
    plan_data["updated_at"] = now_str
    plan_id = "current_plan"

    doc = dict(plan_data)
    doc["id"] = plan_id

    try:
        db.plans.replace_one({"id": plan_id}, doc, upsert=True)
        logger.info(f"Plan saved to MongoDB. Target completion: {plan_data.get('target_completion_date')}")
    except Exception as e:
        logger.error(f"Error saving plan to MongoDB: {e}")
        raise


def get_plan_doc(db, progress_map, slug_map):
    """Retrieve active plan document from MongoDB and reconcile metadata."""
    try:
        doc = db.plans.find_one({"id": "current_plan"}, {"_id": 0})
        if doc and "schedule" in doc:
            needs_update = False
            schedule = doc.get("schedule", [])
            schedule_start_date = schedule[0]["date"] if schedule else None

            # Auto-healing: ensure all 495 syllabus problems are present in schedule
            from src.planner.syllabus import load_flattened_syllabus
            flat_problems, _ = load_flattened_syllabus()
            sched_probs = {prob.get("uid") for day in schedule for prob in day.get("problems", []) if prob.get("uid")}

            if len(sched_probs) < len(flat_problems):
                missing_probs = [dict(p) for p in flat_problems if p["uid"] not in sched_probs]
                logger.info(f"Auto-healing study plan: restoring {len(missing_probs)} missing problems into schedule.")

                first_study_day = next((d for d in schedule if d.get("type") == "study"), None)
                last_study_day = next((d for d in reversed(schedule) if d.get("type") == "study"), None)

                for mp in missing_probs:
                    mp_uid = mp["uid"]
                    prog = progress_map.get(mp_uid) if progress_map else None
                    if prog and prog.get("completed"):
                        mp["completed"] = True
                        mp["completed_at"] = prog.get("completed_at") or datetime.now().isoformat()
                        if prog.get("revision"):
                            mp["revision"] = True
                            mp["revision_marked_at"] = prog.get("revision_marked_at")
                        if first_study_day:
                            first_study_day["problems"].append(mp)
                    else:
                        mp["completed"] = False
                        mp["completed_at"] = None
                        if prog and prog.get("revision"):
                            mp["revision"] = True
                            mp["revision_marked_at"] = prog.get("revision_marked_at")
                        else:
                            mp["revision"] = False
                            mp["revision_marked_at"] = None
                        if last_study_day:
                            last_study_day["problems"].append(mp)

                if first_study_day:
                    first_study_day["est_minutes"] = sum(p.get("est_minutes", 0) for p in first_study_day["problems"])
                    first_study_day["topics"] = list(dict.fromkeys(p["topic"] for p in first_study_day["problems"] if p.get("topic")))
                    first_study_day["completed"] = all(p.get("completed", False) for p in first_study_day["problems"])
                if last_study_day and last_study_day != first_study_day:
                    last_study_day["est_minutes"] = sum(p.get("est_minutes", 0) for p in last_study_day["problems"])
                    last_study_day["topics"] = list(dict.fromkeys(p["topic"] for p in last_study_day["problems"] if p.get("topic")))
                    last_study_day["completed"] = all(p.get("completed", False) for p in last_study_day["problems"])

                doc["total_problems"] = len(flat_problems)
                needs_update = True

            for day in schedule:
                if schedule_start_date:
                    expected_week = compute_week_number(day["date"], schedule_start_date)
                    if day.get("week_number") != expected_week:
                        day["week_number"] = expected_week
                        needs_update = True

                for prob in day.get("problems", []):
                    p_uid = prob.get("uid")
                    if not prob.get("slug"):
                        prob_slug = slug_map.get(prob.get("id"), "")
                        if prob_slug:
                            prob["slug"] = prob_slug
                            needs_update = True

                    if "revision" not in prob:
                        prob["revision"] = False
                        prob["revision_marked_at"] = None

                    # Ensure revision status recorded in progress_map is strictly preserved
                    if progress_map and p_uid in progress_map:
                        prog = progress_map[p_uid]
                        if prog.get("revision") and not prob.get("revision"):
                            prob["revision"] = True
                            prob["revision_marked_at"] = prog.get("revision_marked_at")
                            needs_update = True
                        if prog.get("completed") and not prob.get("completed"):
                            prob["completed"] = True
                            prob["completed_at"] = prog.get("completed_at")
                            needs_update = True

                    if prob.get("article_link"):
                        if prob.get("practice_link") is not None:
                            prob["practice_link"] = None
                            needs_update = True
                    else:
                        expected_practice = f"https://takeuforward.org/practice/dsa/{prob['slug']}" if prob.get("slug") else None
                        if prob.get("practice_link") != expected_practice:
                            prob["practice_link"] = expected_practice
                            needs_update = True

            expected_total_weeks = schedule[-1]["week_number"] if schedule else 0
            if doc.get("total_weeks") != expected_total_weeks:
                doc["total_weeks"] = expected_total_weeks
                needs_update = True

            if needs_update:
                try:
                    db.plans.update_one(
                        {"id": "current_plan"},
                        {"$set": {
                            "schedule": doc["schedule"],
                            "total_weeks": doc["total_weeks"],
                            "total_problems": doc.get("total_problems", len(flat_problems))
                        }}
                    )
                except Exception as e:
                    logger.warning(f"Failed to auto-update week numbers / problem slugs in MongoDB: {e}")
        return doc
    except Exception as e:
        logger.error(f"Error reading plan from MongoDB: {e}")
        return None


def reset_plan_doc(db):
    """Delete current plan and all progress records from MongoDB."""
    try:
        db.plans.delete_many({"id": "current_plan"})
        db.problem_progress.delete_many({})
        logger.info("Active plan and progress data reset in MongoDB.")
        return True
    except Exception as e:
        logger.error(f"Error resetting plan in MongoDB: {e}")
        raise
