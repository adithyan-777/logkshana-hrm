from datetime import date

from django.db.models import Q, QuerySet
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity, WorkSession
from employees.models import Employee


def attendance_activity_list(
    *,
    search: str = "",
    employee: Employee | None = None,
    day_from: date | None = None,
    day_to: date | None = None,
) -> QuerySet[AttendanceActivity]:
    queryset = AttendanceActivity.objects.select_related("employee").order_by(
        "-punch_time"
    )

    if employee is not None:
        queryset = queryset.filter(employee=employee)

    if day_from or day_to:
        queryset = queryset.annotate(
            history_day=Coalesce(
                "attendance__day",
                TruncDate("punch_time", tzinfo=timezone.get_current_timezone()),
            )
        )
        if day_from:
            queryset = queryset.filter(history_day__gte=day_from)
        if day_to:
            queryset = queryset.filter(history_day__lte=day_to)

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
