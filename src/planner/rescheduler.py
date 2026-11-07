from datetime import datetime, timedelta
from src.logger import logger
from src.planner.syllabus import load_flattened_syllabus
from src.planner.calendar_utils import compute_week_number


def update_plan_availability(current_plan, updated_availability, from_date_str=None, pace_multiplier=None, existing_progress_map=None):
    """
    Update plan's weekly availability (number of hours per day and/or active days, e.g. switch to 5-day plan).
    
    Guarantees:
    1. Current progress remains the same:
       - Every completed problem stays completed with its original timestamp.
       - Solved count, topics progress, and completion percentage are unchanged.
    2. IN NO CASE IS A REVISION QUESTION UNMARKED EVER:
       - Every question marked for revision retains its revision status and bookmark.
    3. Reschedules remaining/future days starting from from_date using the new weekly availability:
       - Off days (0.0h) become rest days.
       - Active days become study days with the updated hours.
       - Canonical syllabus order is maintained.
       - Total study days, rest days, total weeks, and target completion date are recalculated.
    """
    if not current_plan:
        raise ValueError("No active plan to update.")

    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    norm_avail = {d: max(0.0, float(updated_availability.get(d, 0.0))) for d in days_order}

    if sum(norm_avail.values()) <= 0:
        raise ValueError("Weekly availability must have at least one study day with hours > 0.")

    today = datetime.now().date()
    plan_start_str = current_plan.get("start_date")
    plan_start = datetime.strptime(str(plan_start_str).split("T")[0], "%Y-%m-%d").date() if plan_start_str else today

    # Determine cutoff date:
    # If explicit from_date_str is given, use it.
    # Otherwise: if plan_start is in future, start from plan_start; else start from today.
    if from_date_str:
        if isinstance(from_date_str, datetime):
            cutoff_date = from_date_str.date()
        else:
            cutoff_date = datetime.strptime(str(from_date_str).split("T")[0], "%Y-%m-%d").date()
    else:
        cutoff_date = plan_start if plan_start > today else today

    # 1. Build comprehensive state lookup (completed + revision) across existing plan and progress map
    state_lookup = {}
    if existing_progress_map:
        for uid, prog in existing_progress_map.items():
            state_lookup[uid] = {
                "completed": bool(prog.get("completed")),
                "completed_at": prog.get("completed_at"),
                "revision": bool(prog.get("revision")),
                "revision_marked_at": prog.get("revision_marked_at")
            }

    for day in current_plan.get("schedule", []):
        for p in day.get("problems", []):
            uid = p.get("uid")
            if not uid:
                continue
            if uid not in state_lookup:
                state_lookup[uid] = {
                    "completed": bool(p.get("completed")),
                    "completed_at": p.get("completed_at"),
                    "revision": bool(p.get("revision")),
                    "revision_marked_at": p.get("revision_marked_at"),
                    "article_link": p.get("article_link"),
                    "practice_link": p.get("practice_link")
                }
            else:
                # Merge: in no case unmark revision or uncomplete
                if p.get("revision"):
                    state_lookup[uid]["revision"] = True
                    if not state_lookup[uid].get("revision_marked_at"):
                        state_lookup[uid]["revision_marked_at"] = p.get("revision_marked_at")
                if p.get("completed"):
                    state_lookup[uid]["completed"] = True
                    if not state_lookup[uid].get("completed_at"):
                        state_lookup[uid]["completed_at"] = p.get("completed_at")
                if p.get("article_link") and not state_lookup[uid].get("article_link"):
                    state_lookup[uid]["article_link"] = p.get("article_link")
                if p.get("practice_link") and not state_lookup[uid].get("practice_link"):
                    state_lookup[uid]["practice_link"] = p.get("practice_link")

    # 2. Preserve ALL history strictly before cutoff_date (both completed and incomplete problems)
    completed_history = []
    history_problem_uids = set()

    for day in current_plan.get("schedule", []):
        day_date_str = day.get("date")
        if not day_date_str:
            continue
        day_date = datetime.strptime(day_date_str.split("T")[0], "%Y-%m-%d").date()

        if day_date < cutoff_date:
            if day.get("type") == "rest":
                completed_history.append(dict(day))
            elif day.get("type") == "study":
                probs = day.get("problems", [])
                preserved_probs = []
                for p in probs:
                    p_uid = p.get("uid")
                    st = state_lookup.get(p_uid, {})
                    preserved_p = dict(p)

                    # Preserve/merge completion status
                    if p.get("completed") or st.get("completed", False):
                        preserved_p["completed"] = True
                        preserved_p["completed_at"] = p.get("completed_at") or st.get("completed_at")

                    # Revision must stay marked — IN NO CASE UNMARKED EVER
                    if st.get("revision") or p.get("revision"):
                        preserved_p["revision"] = True
                        preserved_p["revision_marked_at"] = st.get("revision_marked_at") or p.get("revision_marked_at")

                    preserved_probs.append(preserved_p)
                    history_problem_uids.add(p_uid)

                if preserved_probs:
                    hist_day = dict(day)
                    hist_day["problems"] = preserved_probs
                    hist_day["est_minutes"] = sum(p.get("est_minutes", 0) for p in preserved_probs)
                    hist_day["topics"] = list(dict.fromkeys(p["topic"] for p in preserved_probs if p.get("topic")))
                    hist_day["completed"] = all(p.get("completed", False) for p in preserved_probs)
                    completed_history.append(hist_day)
                else:
                    completed_history.append({
                        "type": "rest",
                        "date": day_date.isoformat(),
                        "day_name": day.get("day_name") or day_date.strftime("%A"),
                        "message": "Missed / Rest Day 🧘"
                    })

    # Collect any problems that are already completed in state_lookup but not yet in completed_history
    # (e.g. completed today, solved ahead of schedule, or completed on future days).
    # These must NOT be scheduled into future study days; they belong in completed history.
    flat_problems, topics_summary = load_flattened_syllabus()
    flat_map = {p["uid"]: p for p in flat_problems}

    unplaced_completed_uids = [
        uid for uid, st in state_lookup.items()
        if st.get("completed") and uid not in history_problem_uids
    ]

    if unplaced_completed_uids:
        cutoff_day_name = cutoff_date.strftime("%A")
        cutoff_probs = []
        for uid in unplaced_completed_uids:
            base_p = flat_map.get(uid, {})
            st = state_lookup.get(uid, {})
            cp = dict(base_p)
            cp["completed"] = True
            cp["completed_at"] = st.get("completed_at") or datetime.now().isoformat()
            if st.get("revision"):
                cp["revision"] = True
                cp["revision_marked_at"] = st.get("revision_marked_at")
            if st.get("article_link"):
                cp["article_link"] = st.get("article_link")
            if st.get("practice_link"):
                cp["practice_link"] = st.get("practice_link")
            cutoff_probs.append(cp)
            history_problem_uids.add(uid)

        hist_study_count = len([d for d in completed_history if d.get("type") == "study"])
        cutoff_day_obj = {
            "type": "study",
            "day_number": hist_study_count + 1,
            "date": cutoff_date.isoformat(),
            "day_name": cutoff_day_name,
            "allocated_hours": norm_avail.get(cutoff_day_name, 2.0),
            "est_minutes": sum(p.get("est_minutes", 0) for p in cutoff_probs),
            "topics": list(dict.fromkeys(p["topic"] for p in cutoff_probs if p.get("topic"))),
            "problems": cutoff_probs,
            "completed": True
        }
        completed_history.append(cutoff_day_obj)
        cur_date = cutoff_date + timedelta(days=1)
    else:
        cur_date = cutoff_date

    # 3. Gather all remaining incomplete problems in canonical syllabus order
    remaining_problems = []

    for p in flat_problems:
        uid = p["uid"]
        if uid in history_problem_uids:
            continue

        merged_p = dict(p)
        st = state_lookup.get(uid, {})

        # Retain completion status (should be False since completed are placed in history)
        if st.get("completed"):
            merged_p["completed"] = True
            merged_p["completed_at"] = st.get("completed_at")
        else:
            merged_p["completed"] = False
            merged_p["completed_at"] = None

        # Retain revision status — IN NO CASE UNMARKED EVER
        if st.get("revision"):
            merged_p["revision"] = True
            merged_p["revision_marked_at"] = st.get("revision_marked_at")
        else:
            merged_p["revision"] = False
            merged_p["revision_marked_at"] = None

        if st.get("article_link"):
            merged_p["article_link"] = st.get("article_link")
        if st.get("practice_link"):
            merged_p["practice_link"] = st.get("practice_link")

        remaining_problems.append(merged_p)

    # 4. Schedule future days from cur_date based on updated_availability
    active_pace = pace_multiplier if pace_multiplier is not None else current_plan.get("pace_multiplier", 1.0)
    prob_idx = 0
    total_remaining = len(remaining_problems)
    new_future_days = []
    next_day_num = len([d for d in completed_history if d.get("type") == "study"]) + 1

    while prob_idx < total_remaining:
        day_name = cur_date.strftime("%A")
        avail_hrs = norm_avail[day_name]

        if avail_hrs <= 0.0:
            new_future_days.append({
                "type": "rest",
                "date": cur_date.isoformat(),
                "day_name": day_name,
                "message": "Rest & Recharge Day 🧘"
            })
            cur_date += timedelta(days=1)
            continue

        avail_mins = int(avail_hrs * 60 * active_pace)
        assigned = []
        spent_mins = 0

        while prob_idx < total_remaining:
            p = remaining_problems[prob_idx]
            p_time = p["est_minutes"]

            if assigned and (spent_mins + p_time > avail_mins * 1.2):
                break

            assigned.append(p)
            spent_mins += p_time
            prob_idx += 1

        topics_in_day = list(dict.fromkeys(p["topic"] for p in assigned if p.get("topic")))
        day_completed = all(p.get("completed", False) for p in assigned) if assigned else False

        new_future_days.append({
            "type": "study",
            "day_number": next_day_num,
            "date": cur_date.isoformat(),
            "day_name": day_name,
            "allocated_hours": avail_hrs,
            "est_minutes": spent_mins,
            "topics": topics_in_day,
            "problems": assigned,
            "completed": day_completed
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
    target_date = combined_schedule[-1]["date"] if combined_schedule else None

    updated_plan = dict(current_plan)
    updated_plan["schedule"] = combined_schedule
    updated_plan["weekly_availability"] = norm_avail
    updated_plan["pace_multiplier"] = active_pace
    updated_plan["total_study_days"] = len(study_days)
    updated_plan["total_rest_days"] = len(rest_days)
    updated_plan["total_calendar_days"] = len(combined_schedule)
    updated_plan["total_weeks"] = total_weeks
    updated_plan["target_completion_date"] = target_date
    updated_plan["is_paused"] = False
    updated_plan["paused_at"] = None

    # Safety invariant: verify that all syllabus problems are present in schedule
    all_scheduled_uids = {p["uid"] for d in combined_schedule for p in d.get("problems", [])}
    if len(all_scheduled_uids) < len(flat_problems):
        missing_syllabus = [dict(p) for p in flat_problems if p["uid"] not in all_scheduled_uids]
        logger.warning(f"Rescheduler detected {len(missing_syllabus)} missing problems. Appending to last study day.")
        last_study_day = next((d for d in reversed(combined_schedule) if d.get("type") == "study"), None)
        if last_study_day is not None:
            for mp in missing_syllabus:
                mp["completed"] = False
                mp["completed_at"] = None
                mp["revision"] = False
                mp["revision_marked_at"] = None
            last_study_day["problems"].extend(missing_syllabus)
            last_study_day["est_minutes"] = sum(p.get("est_minutes", 0) for p in last_study_day["problems"])
            last_study_day["topics"] = list(dict.fromkeys(p["topic"] for p in last_study_day["problems"] if p.get("topic")))

    logger.info(
        f"Updated plan availability starting from {cutoff_date}: "
        f"{len(study_days)} study days, {len(rest_days)} rest days, "
        f"new target finish: {target_date}"
    )
    return updated_plan


def realign_or_resume_plan(current_plan, resume_date_str=None, updated_availability=None):
    """
    Resume or Re-align schedule:
    - Retains all previously completed days and completed problems intact.
    - Preserves all revision questions without ever unmarking them.
    - Re-schedules remaining problems starting from resume_date_str using weekly_availability.
    - Sets is_paused = False.
    """
    if not current_plan:
        raise ValueError("No active plan to resume or realign.")

    availability = updated_availability or current_plan.get("weekly_availability", {})
    return update_plan_availability(current_plan, availability, from_date_str=resume_date_str)
