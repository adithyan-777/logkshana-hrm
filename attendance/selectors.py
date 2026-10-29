from django.db.models import Q, QuerySet

from attendance.models import Attendance, AttendanceActivity, WorkSession
from employees.models import Employee


def attendance_activity_list(
    *, search: str = "", employee: Employee | None = None
) -> QuerySet[AttendanceActivity]:
    queryset = AttendanceActivity.objects.select_related("employee").order_by(
        "-punch_time"
    )

    if employee is not None:
        queryset = queryset.filter(employee=employee)

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
            | Q(external_id__icontains=search)
        )

    return queryset


def attendance_list(
    *, search: str = "", employee: Employee | None = None
) -> QuerySet[Attendance]:
    queryset = Attendance.objects.select_related(
        "employee", "shift"
    ).order_by("-day")

    if employee is not None:
        queryset = queryset.filter(employee=employee)

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
            | Q(status__icontains=search)
        )

    return queryset


def work_session_list(*, search: str = "") -> QuerySet[WorkSession]:
    queryset = WorkSession.objects.select_related(
        "employee", "in_punch", "out_punch"
    ).order_by("-day", "-check_in")

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
        )

    return queryset