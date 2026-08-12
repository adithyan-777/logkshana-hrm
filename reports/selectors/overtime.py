from datetime import date

from django.db.models import Count, Q, Sum

from attendance.models import OvertimeRecord


def overtime_report_list(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
    status: str = "",
):
    queryset = OvertimeRecord.objects.filter(
        date__range=(date_from, date_to),
    ).select_related("employee", "employee__department", "daily_attendance")

    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)
    if status:
        queryset = queryset.filter(status=status)

    return queryset.order_by("-date", "employee__first_name")


def overtime_summary_by_employee(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
    status: str = "",
):
    queryset = OvertimeRecord.objects.filter(date__range=(date_from, date_to))

    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)
    if status:
        queryset = queryset.filter(status=status)

    return (
        queryset.values(
            "employee_id",
            "employee__emp_code",
            "employee__first_name",
            "employee__last_name",
            "employee__department__name",
        )
        .annotate(
            record_count=Count("id"),
            total_minutes=Sum("minutes"),
        )
        .order_by("employee__first_name", "employee__last_name")
    )
