from datetime import datetime


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
