from datetime import date, timedelta

from django.db.models import Count, Sum

from attendance.models import Attendance


def _overtime_base_queryset(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
    status: str = "",
):
    queryset = Attendance.objects.filter(
        day__range=(date_from, date_to),
        over_time__gt=timedelta(0),
    ).select_related("employee", "employee__department")

    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)
    if status:
        queryset = queryset.filter(status=status)

    return queryset


def overtime_report_list(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
    status: str = "",
):
    return _overtime_base_queryset(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        employee_id=employee_id,
        status=status,
    ).order_by("-day", "employee__first_name")


def overtime_summary_by_employee(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
    status: str = "",
):
    return (
        _overtime_base_queryset(
            date_from=date_from,
            date_to=date_to,
            department_id=department_id,
            employee_id=employee_id,
            status=status,
        )
        .values(
            "employee_id",
            "employee__emp_code",
            "employee__first_name",
            "employee__last_name",
            "employee__department__name",
        )
        .annotate(
            record_count=Count("id"),
            total_overtime=Sum("over_time"),
        )
        .order_by("employee__first_name", "employee__last_name")
    )
