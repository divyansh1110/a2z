import json
import re
import os
from datetime import datetime, timedelta
from src.logger import logger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SYLLABUS_PATH = os.path.join(PROJECT_ROOT, "data", "full_dsa_sheet_syllabus.json")

def parse_duration_to_minutes(dur_str, difficulty):
    """Parse duration string or return an estimate based on difficulty."""
    if dur_str:
        m = re.search(r'(\d+)\s*min', str(dur_str).lower())
        if m:
            return int(m.group(1))
    diff = (difficulty or '').lower()
    if diff == 'basic':
        return 30
    elif diff == 'core':
        return 45
    elif diff == 'pro':
        return 60
    return 35

def load_flattened_syllabus(filepath=DEFAULT_SYLLABUS_PATH):
    """Load and flatten all problems from the syllabus JSON."""
    if not os.path.exists(filepath):
        logger.error(f"Syllabus file not found at {filepath}")
        raise FileNotFoundError(f"Syllabus file not found at: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        syllabus = json.load(f)

    flat_problems = []
    topics_summary = []
    idx = 0

    for topic_order, topic in enumerate(syllabus, 1):
        topic_name = topic.get("topic", "").strip()
        topic_slug = topic.get("slug", "")
        topic_problems_count = 0
        subtopics_summary = []

        for sub_order, sub in enumerate(topic.get("subtopics", []), 1):
            sub_name = sub.get("subtopic", "").strip()
            sub_slug = sub.get("slug", "")
            sub_probs = sub.get("problems", [])
            topic_problems_count += len(sub_probs)

            subtopics_summary.append({
                "id": sub.get("id"),
                "subtopic": sub_name,
                "slug": sub_slug,
                "problem_count": len(sub_probs)
            })

            for p in sub_probs:
                idx += 1
                est_mins = parse_duration_to_minutes(p.get("duration"), p.get("difficulty"))
                uid = f"p_{idx}_{p.get('id')}"

                tag = p.get("tag")
                if not tag:
                    diff = p.get("difficulty")
                    tag = diff.capitalize() if diff else "Basic"

                prob_slug = p.get("slug", "")
                article_link = p.get("article_link")
                practice_link = (
                    f"https://takeuforward.org/practice/dsa/{prob_slug}"
                    if prob_slug and not article_link
                    else None
                )

                flat_problems.append({
                    "uid": uid,
                    "id": p.get("id"),
                    "title": p.get("title", "").strip(),
                    "slug": prob_slug,
                    "practice_link": practice_link,
                    "topic_order": topic_order,
                    "topic": topic_name,
                    "topic_slug": topic_slug,
                    "subtopic_order": sub_order,
                    "subtopic": sub_name,
                    "subtopic_slug": sub_slug,
                    "difficulty": (p.get("difficulty") or "basic").lower(),
                    "tag": tag,
                    "duration": p.get("duration"),
                    "est_minutes": est_mins,
                    "leetcode_link": p.get("leetcode_link"),
                    "youtube_link": p.get("youtube_link"),
                    "article_link": p.get("article_link"),
                    "completed": False,
                    "completed_at": None,
                    "revision": False,
                    "revision_marked_at": None
                })

        topics_summary.append({
            "order": topic_order,
            "id": topic.get("id"),
            "topic": topic_name,
            "slug": topic_slug,
            "subtopics": subtopics_summary,
            "total_problems": topic_problems_count
        })

    logger.info(f"Loaded syllabus: {len(topics_summary)} topics, {len(flat_problems)} total problems.")
    return flat_problems, topics_summary

def generate_plan(weekly_availability, start_date_str=None, pace_multiplier=1.0):
    """
    Generate a full personalized study schedule based on user's weekly availability.
    weekly_availability: {"Monday": 2.0, "Tuesday": 1.5, ...}
    start_date_str: "YYYY-MM-DD" (defaults to today)
    """
    flat_problems, topics_summary = load_flattened_syllabus()

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

    cal_day_idx = 0

    while prob_idx < total_problems:
        day_name = cur_date.strftime("%A")
        avail_hrs = norm_avail[day_name]
        week_num = (cal_day_idx // 7) + 1

        if avail_hrs <= 0.0:
            schedule.append({
                "type": "rest",
                "week_number": week_num,
                "date": cur_date.isoformat(),
                "day_name": day_name,
                "message": "Rest & Recharge Day 🧘"
            })
            cur_date += timedelta(days=1)
            cal_day_idx += 1
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
            "completed": False
        })
        day_num += 1
        cur_date += timedelta(days=1)
        cal_day_idx += 1

    study_days = [d for d in schedule if d["type"] == "study"]
    rest_days = [d for d in schedule if d["type"] == "rest"]
    total_weeks = (len(schedule) + 6) // 7 if schedule else 0

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

def realign_or_resume_plan(current_plan, resume_date_str=None, updated_availability=None):
    """
    Resume or Re-align schedule:
    - Retains all previously completed days and completed problems intact.
    - Gathers remaining incomplete problems.
    - Re-schedules incomplete problems starting from resume_date_str using weekly_availability.
    - Sets is_paused = False.
    """
    if not current_plan:
        raise ValueError("No active plan to resume or realign.")

    if not resume_date_str:
        resume_date = datetime.now().date()
    else:
        resume_date = datetime.strptime(resume_date_str, "%Y-%m-%d").date()

    availability = updated_availability or current_plan.get("weekly_availability", {})
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    norm_avail = {d: max(0.0, float(availability.get(d, 0.0))) for d in days_order}

    if sum(norm_avail.values()) <= 0:
        raise ValueError("Weekly availability must have at least one study day with hours > 0.")

    existing_schedule = current_plan.get("schedule", [])
    completed_history = []
    remaining_problems = []

    for day in existing_schedule:
        if day.get("type") == "rest":
            day_d = datetime.strptime(day["date"], "%Y-%m-%d").date()
            if day_d < resume_date:
                completed_history.append(day)
        elif day.get("type") == "study":
            day_d = datetime.strptime(day["date"], "%Y-%m-%d").date()
            if day.get("completed") and day_d < resume_date:
                completed_history.append(day)
            else:
                for p in day.get("problems", []):
                    remaining_problems.append(p)

    history_problem_uids = set()
    for d in completed_history:
        for p in d.get("problems", []):
            history_problem_uids.add(p["uid"])

    uncompleted_problems = [p for p in remaining_problems if p["uid"] not in history_problem_uids and not p.get("completed")]
    already_done_in_uncompleted = [p for p in remaining_problems if p["uid"] not in history_problem_uids and p.get("completed")]

    all_to_schedule = already_done_in_uncompleted + uncompleted_problems

    cur_date = resume_date
    prob_idx = 0
    next_day_num = len([d for d in completed_history if d.get("type") == "study"]) + 1
    new_schedule_days = []
    pace_multiplier = current_plan.get("pace_multiplier", 1.0)

    while prob_idx < len(all_to_schedule):
        day_name = cur_date.strftime("%A")
        avail_hrs = norm_avail[day_name]

        if avail_hrs <= 0.0:
            new_schedule_days.append({
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

        while prob_idx < len(all_to_schedule):
            p = all_to_schedule[prob_idx]
            p_time = p["est_minutes"]

            if assigned and (spent_mins + p_time > avail_mins * 1.2):
                break

            assigned.append(p)
            spent_mins += p_time
            prob_idx += 1

        topics_in_day = list(dict.fromkeys(p["topic"] for p in assigned))
        day_completed = all(p.get("completed", False) for p in assigned)

        new_schedule_days.append({
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

    combined_schedule = completed_history + new_schedule_days
    for idx, d in enumerate(combined_schedule):
        d["week_number"] = (idx // 7) + 1

    study_days = [d for d in combined_schedule if d["type"] == "study"]
    rest_days = [d for d in combined_schedule if d["type"] == "rest"]
    total_weeks = (len(combined_schedule) + 6) // 7 if combined_schedule else 0

    updated_plan = dict(current_plan)
    updated_plan["schedule"] = combined_schedule
    updated_plan["is_paused"] = False
    updated_plan["paused_at"] = None
    updated_plan["weekly_availability"] = norm_avail
    updated_plan["total_study_days"] = len(study_days)
    updated_plan["total_rest_days"] = len(rest_days)
    updated_plan["total_calendar_days"] = len(combined_schedule)
    updated_plan["total_weeks"] = total_weeks
    updated_plan["target_completion_date"] = combined_schedule[-1]["date"] if combined_schedule else None

    logger.info(
        f"Realigned/resumed plan starting from {resume_date}: "
        f"{len(study_days)} total study days, new finish date: {updated_plan['target_completion_date']}"
    )
    return updated_plan

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
        if existing_p and existing_p.get("completed"):
            continue

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
    for idx, d in enumerate(combined_schedule):
        d["week_number"] = (idx // 7) + 1

    study_days = [d for d in combined_schedule if d["type"] == "study"]
    rest_days = [d for d in combined_schedule if d["type"] == "rest"]
    total_weeks = (len(combined_schedule) + 6) // 7 if combined_schedule else 0
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

def compute_metrics(plan, current_date_str=None):
    """Compute live completion statistics, today's schedule, and topic progress."""
    if not plan:
        return None

    if not current_date_str:
        today_date = datetime.now().date().isoformat()
    else:
        today_date = current_date_str

    schedule = plan.get("schedule", [])
    total_problems = plan.get("total_problems", 495)
    completed_problems = 0
    completed_study_days = 0
    total_study_days = 0
    revision_problems = 0

    today_day_data = None
    next_pending_day = None

    topic_stats = {}
    for t in plan.get("topics_summary", []):
        topic_stats[t["topic"]] = {"total": t["total_problems"], "completed": 0}

    for day in schedule:
        if day.get("type") == "study":
            total_study_days += 1
            all_done = True
            for p in day.get("problems", []):
                if p.get("revision"):
                    revision_problems += 1
                if p.get("completed"):
                    completed_problems += 1
                    t_name = p.get("topic")
                    if t_name in topic_stats:
                        topic_stats[t_name]["completed"] += 1
                else:
                    all_done = False
            if all_done and day.get("problems"):
                completed_study_days += 1

            if not next_pending_day and not all_done:
                next_pending_day = day

        if day.get("date") == today_date:
            today_day_data = day

    active_focus_day = today_day_data if (today_day_data and today_day_data.get("type") == "study") else next_pending_day

    pct = round((completed_problems / total_problems * 100), 1) if total_problems else 0.0

    return {
        "today_date": today_date,
        "is_paused": plan.get("is_paused", False),
        "paused_at": plan.get("paused_at"),
        "total_problems": total_problems,
        "completed_problems": completed_problems,
        "revision_problems": revision_problems,
        "remaining_problems": total_problems - completed_problems,
        "completion_percent": pct,
        "total_study_days": total_study_days,
        "completed_study_days": completed_study_days,
        "remaining_study_days": total_study_days - completed_study_days,
        "target_completion_date": plan.get("target_completion_date"),
        "today_day_data": today_day_data,
        "active_focus_day": active_focus_day,
        "topic_progress": topic_stats
    }
