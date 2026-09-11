from datetime import date

from django.db.models import Q, QuerySet

from attendance.models import DailyAttendance
from reports.selectors.attendance import _daily_attendance_base_queryset


def exception_report_list(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
    exception_type: str = "",
) -> QuerySet[DailyAttendance]:
    queryset = _daily_attendance_base_queryset(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        employee_id=employee_id,
    )

    if exception_type == "late":
        queryset = queryset.filter(status=DailyAttendance.Status.LATE)
    elif exception_type == "absent":
        queryset = queryset.filter(status=DailyAttendance.Status.ABSENT)
    elif exception_type == "incomplete":
        queryset = queryset.filter(status=DailyAttendance.Status.INCOMPLETE)
    elif exception_type == "missing_punch":
        queryset = queryset.filter(Q(has_check_in=False) | Q(has_check_out=False))
    else:
        queryset = queryset.filter(
            Q(
                status__in=[
                    DailyAttendance.Status.LATE,
                    DailyAttendance.Status.ABSENT,
                    DailyAttendance.Status.INCOMPLETE,
                ]
            )
            | Q(has_check_in=False)
            | Q(has_check_out=False)
        )

    return queryset.order_by("-date", "employee__first_name")
