from datetime import datetime, timedelta
from src.logger import logger
from src.planner.syllabus import load_flattened_syllabus
from src.planner.calendar_utils import compute_week_number


def generate_plan(weekly_availability, start_date_str=None, pace_multiplier=1.0, existing_progress_map=None):
    """
    Generate a full personalized study schedule based on user's weekly availability.
    weekly_availability: {"Monday": 2.0, "Tuesday": 1.5, ...}
    start_date_str: "YYYY-MM-DD" (defaults to today)
    existing_progress_map: optional dict {uid: {"completed": bool, "completed_at": str, "revision": bool, "revision_marked_at": str}}
    """
    flat_problems, topics_summary = load_flattened_syllabus()

    # Preserve any existing progress and revision bookmarks
    if existing_progress_map:
        for p in flat_problems:
            prog = existing_progress_map.get(p["uid"])
            if prog:
                if prog.get("completed"):
                    p["completed"] = True
                    p["completed_at"] = prog.get("completed_at")
                if prog.get("revision"):
                    p["revision"] = True
                    p["revision_marked_at"] = prog.get("revision_marked_at")

    if not start_date_str:
        start_date = datetime.now().date()
    else:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

    # Normalize availability
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    norm_avail = {}
    for d in days_order:
        norm_avail[d] = max(0.0, float(weekly_availability.get(d, 0.0)))

    total_avail_hours = sum(norm_avail.values())
    if total_avail_hours <= 0:
        logger.warning("Attempted to generate plan with 0 hours weekly availability.")
        raise ValueError("Please select at least one day with more than 0 hours available.")

    cur_date = start_date
    prob_idx = 0
    day_num = 1
    schedule = []
    total_problems = len(flat_problems)

    while prob_idx < total_problems:
        day_name = cur_date.strftime("%A")
        avail_hrs = norm_avail[day_name]
        week_num = compute_week_number(cur_date, start_date)

        if avail_hrs <= 0.0:
            schedule.append({
                "type": "rest",
                "week_number": week_num,
                "date": cur_date.isoformat(),
                "day_name": day_name,
                "message": "Rest & Recharge Day 🧘"
            })
            cur_date += timedelta(days=1)
            continue

        avail_mins = int(avail_hrs * 60 * pace_multiplier)
        assigned = []
        spent_mins = 0

        while prob_idx < total_problems:
            p = flat_problems[prob_idx]
            p_time = p["est_minutes"]

            if assigned and (spent_mins + p_time > avail_mins * 1.2):
                break

            assigned.append(p)
            spent_mins += p_time
            prob_idx += 1

        topics_in_day = list(dict.fromkeys(p["topic"] for p in assigned))
        day_completed = all(p.get("completed", False) for p in assigned) if assigned else False

        schedule.append({
            "type": "study",
            "week_number": week_num,
            "day_number": day_num,
            "date": cur_date.isoformat(),
            "day_name": day_name,
            "allocated_hours": avail_hrs,
            "est_minutes": spent_mins,
            "topics": topics_in_day,
            "problems": assigned,
            "completed": day_completed
        })
        day_num += 1
        cur_date += timedelta(days=1)

    study_days = [d for d in schedule if d["type"] == "study"]
    rest_days = [d for d in schedule if d["type"] == "rest"]
    total_weeks = schedule[-1]["week_number"] if schedule else 0

    plan = {
        "created_at": datetime.now().isoformat(),
        "start_date": start_date.isoformat(),
        "target_completion_date": schedule[-1]["date"] if schedule else None,
        "weekly_availability": norm_avail,
        "pace_multiplier": pace_multiplier,
        "is_paused": False,
        "paused_at": None,
        "total_problems": total_problems,
        "total_study_days": len(study_days),
        "total_rest_days": len(rest_days),
        "total_calendar_days": len(schedule),
        "total_weeks": total_weeks,
        "topics_summary": topics_summary,
        "schedule": schedule
    }

    logger.info(
        f"Generated plan: {len(study_days)} study days, {len(rest_days)} rest days, "
        f"finishing on {plan['target_completion_date']} with {total_avail_hours}h/week"
    )
    return plan
