from datetime import date

from django.db.models import QuerySet

from attendance.models import WorkSession


def work_session_report_list(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
) -> QuerySet[WorkSession]:
    """Work sessions (check-in to check-out pairs) within the reported days."""
    queryset = WorkSession.objects.filter(day__range=(date_from, date_to))
    queryset = queryset.select_related("employee", "employee__department")

    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    return queryset.order_by("-day", "-check_in", "employee__emp_code")
