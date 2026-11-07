from datetime import datetime, timedelta


def compute_week_number(day_date, start_date):
    """
    Calculate 1-based week number where weeks strictly run Monday to Sunday.
    Week 1 begins on start_date and ends on the next Sunday.
    Every subsequent Monday begins a new week.
    """
    if isinstance(day_date, str):
        day_date = datetime.strptime(day_date.split("T")[0], "%Y-%m-%d").date()
    elif isinstance(day_date, datetime):
        day_date = day_date.date()
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date.split("T")[0], "%Y-%m-%d").date()
    elif isinstance(start_date, datetime):
        start_date = start_date.date()

    start_monday = start_date - timedelta(days=start_date.weekday())
    day_monday = day_date - timedelta(days=day_date.weekday())
    return (day_monday - start_monday).days // 7 + 1
