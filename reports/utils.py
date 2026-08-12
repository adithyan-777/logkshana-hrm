from datetime import date

from django.utils import timezone


def current_month_range() -> tuple[date, date]:
    today = timezone.localdate()
    start = today.replace(day=1)
    return start, today


def format_minutes(minutes: int | None) -> str:
    if minutes is None:
        return ""
    hours, mins = divmod(int(minutes), 60)
    return f"{hours}:{mins:02d}"


def format_datetime(value) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M")
