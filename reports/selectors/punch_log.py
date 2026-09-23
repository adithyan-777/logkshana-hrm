from datetime import date

from django.db.models import QuerySet

from attendance.models import AttendanceActivity


def punch_log_list(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
) -> QuerySet[AttendanceActivity]:
    queryset = AttendanceActivity.objects.filter(
        punch_time__date__range=(date_from, date_to),
    ).select_related("employee", "employee__department")

    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    return queryset.order_by("-punch_time")
