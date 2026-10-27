from datetime import date, datetime, time, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from attendance.models import AttendanceActivity


def _punch_time_range(*, date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Half-open local-time bounds for the reported days.

    A plain range lookup (index-usable on ``act_punch_time_idx``)
    replaces ``punch_time__date__range``, which cannot use the b-tree.
    """
    start = timezone.make_aware(datetime.combine(date_from, time.min))
    end = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min))
    return start, end


def punch_log_list(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
) -> QuerySet[AttendanceActivity]:
    start, end = _punch_time_range(date_from=date_from, date_to=date_to)
    queryset = AttendanceActivity.objects.filter(
        punch_time__range=(start, end),
    ).select_related("employee", "employee__department")

    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    return queryset.order_by("-punch_time")
