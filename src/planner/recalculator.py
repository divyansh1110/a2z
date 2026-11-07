from datetime import datetime, timedelta
from src.logger import logger
from src.planner.syllabus import load_flattened_syllabus
from src.planner.calendar_utils import compute_week_number


def recalculate_future_schedule(plan, today_date_str=None, problem_completed_uid=None, force_recalculate=False):
    """
    Recalculates the study plan dynamically in real time when a problem is completed ahead of schedule.

    Rules:
    1. Identify 'Today':
       - Match day in schedule by date == today_date_str (defaults to today's real date).
       - If today is a rest day, or if today_date_str is not in the schedule:
         falls back to the active focus study day (earliest incomplete study day).
    2. Ahead-of-schedule check:
       - Find the day containing problem_completed_uid.
       - If that day is strictly after Today's day (day_idx > today_idx):
         - Remove problem from that future day.
         - Append problem to Today's problems list, marked completed=True with current timestamp.
         - Recalculate Today's est_minutes, topics, and completed state.
         - Set was_moved_to_today = True.
    3. Sequential forward-fill:
       - If was_moved_to_today or force_recalculate:
         - Freeze all days up to and including Today intact.
         - Collect all problem UIDs present in history (completed or pending backlog).
         - Gather all remaining uncompleted syllabus problems in strict canonical order.
         - Pack starting from the calendar day after Today based on weekly_availability & pace_multiplier.
         - Future days automatically backfill with next pending questions.
         - Re-index week_number and study day_number.
         - Update target_completion_date, total_study_days, total_rest_days, total_calendar_days, total_weeks.
    Returns: (updated_plan, was_recalculated, was_moved_to_today, old_target_date, new_target_date)
    """
    if not plan or not plan.get("schedule"):
        return plan, False, False, None, None

    schedule = [dict(d) for d in plan.get("schedule", [])]
    # Deep copy problems within days
    for d in schedule:
        if "problems" in d:
            d["problems"] = [dict(p) for p in d["problems"]]

    old_target_date = plan.get("target_completion_date")

    if not today_date_str:
        today_date_str = datetime.now().date().isoformat()

    # 1. Identify "Today" in schedule
    today_day_idx = None
    for idx, day in enumerate(schedule):
        if day.get("date") == today_date_str:
            today_day_idx = idx
            break

    # If matched day is rest day, or no match found: fallback to active pending study day
    if today_day_idx is None or schedule[today_day_idx].get("type") != "study":
        pending_idx = next(
            (idx for idx, d in enumerate(schedule) if d.get("type") == "study" and not d.get("completed")),
            None
        )
        if pending_idx is not None:
            today_day_idx = pending_idx
        elif today_day_idx is None:
            # Fallback to first study day or day 0
            study_idx = next((idx for idx, d in enumerate(schedule) if d.get("type") == "study"), 0)
            today_day_idx = study_idx

    # 2. Locate problem_completed_uid if provided
    found_day_idx = None
    found_prob = None
    if problem_completed_uid:
        for idx, day in enumerate(schedule):
            if day.get("type") == "study":
                for p in day.get("problems", []):
                    if p.get("uid") == problem_completed_uid:
                        found_day_idx = idx
                        found_prob = p
                        break
            if found_prob:
                break

    was_moved_to_today = False
    if found_prob and found_day_idx is not None and found_day_idx > today_day_idx:
        # Problem is ahead of time in a future day!
        # Remove from future day
        schedule[found_day_idx]["problems"] = [
            p for p in schedule[found_day_idx]["problems"] if p.get("uid") != problem_completed_uid
        ]

        # Append to Today's day
        now_iso = datetime.now().isoformat()
        found_prob["completed"] = True
        found_prob["completed_at"] = now_iso
        schedule[today_day_idx]["problems"].append(found_prob)

        # Refresh Today's day totals
        today_probs = schedule[today_day_idx]["problems"]
        schedule[today_day_idx]["est_minutes"] = sum(p.get("est_minutes", 0) for p in today_probs)
        schedule[today_day_idx]["topics"] = list(dict.fromkeys(p["topic"] for p in today_probs if p.get("topic")))
        schedule[today_day_idx]["completed"] = all(p.get("completed", False) for p in today_probs)

        was_moved_to_today = True

    # Check if any other future days contain completed problems (e.g. from bulk completion or reschedule)
    for fut_idx in range(today_day_idx + 1, len(schedule)):
        if schedule[fut_idx].get("type") == "study":
            fut_probs = schedule[fut_idx].get("problems", [])
            moved_probs = [p for p in fut_probs if p.get("completed")]
            if moved_probs:
                schedule[fut_idx]["problems"] = [p for p in fut_probs if not p.get("completed")]
                schedule[today_day_idx]["problems"].extend(moved_probs)
                was_moved_to_today = True

    if was_moved_to_today:
        today_probs = schedule[today_day_idx]["problems"]
        schedule[today_day_idx]["est_minutes"] = sum(p.get("est_minutes", 0) for p in today_probs)
        schedule[today_day_idx]["topics"] = list(dict.fromkeys(p["topic"] for p in today_probs if p.get("topic")))
        schedule[today_day_idx]["completed"] = all(p.get("completed", False) for p in today_probs)

    if not was_moved_to_today and not force_recalculate:
        updated_plan = dict(plan)
        updated_plan["schedule"] = schedule
        return updated_plan, False, False, old_target_date, old_target_date

    # 3. Sequential forward-fill from the day after Today
    completed_history = schedule[:today_day_idx + 1]

    # Collect all problem UIDs in history
    history_uids = set()
    for d in completed_history:
        for p in d.get("problems", []):
            history_uids.add(p["uid"])

    # Load canonical syllabus problems to maintain strict topic/problem order
    flat_problems, _ = load_flattened_syllabus()

    # Build lookup map of all existing problems to preserve user flags (revision, links)
    prob_lookup = {}
    for d in schedule:
        for p in d.get("problems", []):
            prob_lookup[p["uid"]] = p

    # Filter remaining incomplete problems in canonical order
    remaining_problems = []
    for p in flat_problems:
        uid = p["uid"]
        if uid in history_uids:
            continue
        existing_p = prob_lookup.get(uid)

        merged_p = dict(existing_p if existing_p else p)
        merged_p["completed"] = False
        merged_p["completed_at"] = None
        remaining_problems.append(merged_p)

    # Calculate starting calendar date for future packing
    last_hist_date_str = completed_history[-1]["date"]
    last_hist_date = datetime.strptime(last_hist_date_str, "%Y-%m-%d").date()
    cur_date = last_hist_date + timedelta(days=1)

    # Next study day number
    history_study_days = [d for d in completed_history if d.get("type") == "study"]
    next_day_num = len(history_study_days) + 1

    availability = plan.get("weekly_availability", {})
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    norm_avail = {d: max(0.0, float(availability.get(d, 0.0))) for d in days_order}
    pace_multiplier = plan.get("pace_multiplier", 1.0)

    if sum(norm_avail.values()) <= 0:
        norm_avail = {"Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0, "Thursday": 2.0, "Friday": 2.0, "Saturday": 2.0, "Sunday": 2.0}

    prob_idx = 0
    total_to_schedule = len(remaining_problems)
    new_future_days = []

    while prob_idx < total_to_schedule:
        day_name = cur_date.strftime("%A")
        avail_hrs = norm_avail.get(day_name, 0.0)

        if avail_hrs <= 0.0:
            new_future_days.append({
                "type": "rest",
                "date": cur_date.isoformat(),
                "day_name": day_name,
                "message": "Rest & Recharge Day 🧘"
            })
            cur_date += timedelta(days=1)
            continue

        avail_mins = int(avail_hrs * 60 * pace_multiplier)
        assigned = []
        spent_mins = 0

        while prob_idx < total_to_schedule:
            p = remaining_problems[prob_idx]
            p_time = p["est_minutes"]

            if assigned and (spent_mins + p_time > avail_mins * 1.2):
                break

            assigned.append(p)
            spent_mins += p_time
            prob_idx += 1

        topics_in_day = list(dict.fromkeys(p["topic"] for p in assigned if p.get("topic")))
        new_future_days.append({
            "type": "study",
            "day_number": next_day_num,
            "date": cur_date.isoformat(),
            "day_name": day_name,
            "allocated_hours": avail_hrs,
            "est_minutes": spent_mins,
            "topics": topics_in_day,
            "problems": assigned,
            "completed": False
        })
        next_day_num += 1
        cur_date += timedelta(days=1)

    combined_schedule = completed_history + new_future_days
    if combined_schedule:
        schedule_start_date = combined_schedule[0]["date"]
        for d in combined_schedule:
            d["week_number"] = compute_week_number(d["date"], schedule_start_date)

    study_days = [d for d in combined_schedule if d["type"] == "study"]
    rest_days = [d for d in combined_schedule if d["type"] == "rest"]
    total_weeks = combined_schedule[-1]["week_number"] if combined_schedule else 0
    new_target_date = combined_schedule[-1]["date"] if combined_schedule else None

    updated_plan = dict(plan)
    updated_plan["schedule"] = combined_schedule
    updated_plan["total_study_days"] = len(study_days)
    updated_plan["total_rest_days"] = len(rest_days)
    updated_plan["total_calendar_days"] = len(combined_schedule)
    updated_plan["total_weeks"] = total_weeks
    updated_plan["target_completion_date"] = new_target_date

    logger.info(
        f"Dynamic real-time recalculation complete: {len(study_days)} study days, "
        f"old finish date: {old_target_date} -> new finish date: {new_target_date}"
    )

    return updated_plan, True, was_moved_to_today, old_target_date, new_target_date
