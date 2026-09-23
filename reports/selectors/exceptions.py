from datetime import date

from django.db.models import QuerySet

from attendance.models import Attendance
from reports.selectors.attendance import _attendance_base_queryset


def exception_report_list(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
    exception_type: str = "",
) -> QuerySet[Attendance]:
    queryset = _attendance_base_queryset(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        employee_id=employee_id,
    )

    if exception_type == "late":
        queryset = queryset.filter(status=Attendance.Status.LATE)
    elif exception_type == "absent":
        queryset = queryset.filter(status=Attendance.Status.ABSENT)
    elif exception_type in ("incomplete", "missing_punch"):
        # An incomplete day is the missing-punch signal: a check-in
        # without its check-out (or vice versa).
        queryset = queryset.filter(status=Attendance.Status.INCOMPLETE)
    else:
        queryset = queryset.filter(
            status__in=[
                Attendance.Status.LATE,
                Attendance.Status.ABSENT,
                Attendance.Status.INCOMPLETE,
            ]
        )

    return queryset.order_by("-day", "employee__first_name")
