"""
Planner module for Planly DSA Scheduler.
Provides syllabus loading, calendar calculations, plan generation,
rescheduling, ahead-of-schedule dynamic recalculations, and metrics.
"""

from src.planner.syllabus import (
    DEFAULT_SYLLABUS_PATH,
    parse_duration_to_minutes,
    load_flattened_syllabus,
)
from src.planner.calendar_utils import compute_week_number
from src.planner.generator import generate_plan
from src.planner.rescheduler import (
    update_plan_availability,
    realign_or_resume_plan,
)
from src.planner.recalculator import recalculate_future_schedule
from src.planner.metrics import compute_metrics

__all__ = [
    "DEFAULT_SYLLABUS_PATH",
    "parse_duration_to_minutes",
    "load_flattened_syllabus",
    "compute_week_number",
    "generate_plan",
    "update_plan_availability",
    "realign_or_resume_plan",
    "recalculate_future_schedule",
    "compute_metrics",
]
