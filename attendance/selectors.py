from django.db.models import Q, QuerySet

from attendance.models import (
    AttendanceCorrection,
    AttendanceRule,
    AttendanceTransaction,
    DailyAttendance,
)


def attendance_transaction_list(*, search: str = "") -> QuerySet[AttendanceTransaction]:
    queryset = AttendanceTransaction.objects.select_related("employee").order_by(
        "-timestamp"
    )

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
            | Q(external_id__icontains=search)
        )

    return queryset


def daily_attendance_list(*, search: str = "") -> QuerySet[DailyAttendance]:
    queryset = DailyAttendance.objects.select_related(
        "employee", "shift", "timetable"
    ).order_by("-date")

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
            | Q(status__icontains=search)
        )

    return queryset


def attendance_correction_list(*, search: str = "") -> QuerySet[AttendanceCorrection]:
    queryset = AttendanceCorrection.objects.select_related("employee").order_by(
        "-date"
    )

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
            | Q(reason__icontains=search)
            | Q(status__icontains=search)
        )

    return queryset


def attendance_rule_list(*, search: str = "") -> QuerySet[AttendanceRule]:
    queryset = AttendanceRule.objects.order_by("name")

    if search:
        queryset = queryset.filter(Q(name__icontains=search))

    return queryset
