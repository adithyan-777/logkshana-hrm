from datetime import date

from django.http import HttpRequest
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


def pagination_query_string(request: HttpRequest, page: int) -> str:
    params = request.GET.copy()
    params["page"] = page
    params.pop("format", None)
    return params.urlencode()


def report_pagination_context(request: HttpRequest, page_obj) -> dict:
    context = {
        "page_obj": page_obj,
        "pagination_mode": "link",
    }
    if page_obj.has_previous():
        context["prev_page_url"] = f"?{pagination_query_string(request, page_obj.previous_page_number)}"
    if page_obj.has_next():
        context["next_page_url"] = f"?{pagination_query_string(request, page_obj.next_page_number)}"
    return context
