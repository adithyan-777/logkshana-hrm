from datetime import date

from django.db.models import Count, Q, QuerySet, Sum

from attendance.models import DailyAttendance


def _daily_attendance_base_queryset(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
) -> QuerySet[DailyAttendance]:
    queryset = DailyAttendance.objects.filter(
        date__range=(date_from, date_to),
    ).select_related("employee", "employee__department")

    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    return queryset


def attendance_summary_list(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
):
    return (
        _daily_attendance_base_queryset(
            date_from=date_from,
            date_to=date_to,
            department_id=department_id,
            employee_id=employee_id,
        )
        .values(
            "employee_id",
            "employee__emp_code",
            "employee__first_name",
            "employee__last_name",
            "employee__department__name",
        )
        .annotate(
            total_days=Count("id"),
            present_days=Count("id", filter=Q(status=DailyAttendance.Status.PRESENT)),
            absent_days=Count("id", filter=Q(status=DailyAttendance.Status.ABSENT)),
            late_days=Count("id", filter=Q(status=DailyAttendance.Status.LATE)),
            leave_days=Count("id", filter=Q(status=DailyAttendance.Status.LEAVE)),
            total_worked_minutes=Sum("worked_minutes"),
            total_late_minutes=Sum("late_minutes"),
            total_overtime_minutes=Sum("overtime_minutes"),
        )
        .order_by("employee__first_name", "employee__last_name")
    )


def individual_attendance_list(
    *,
    date_from: date,
    date_to: date,
    employee_id: int,
):
    return _daily_attendance_base_queryset(
        date_from=date_from,
        date_to=date_to,
        employee_id=employee_id,
    ).order_by("date")


def department_attendance_list(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
):
    queryset = _daily_attendance_base_queryset(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
    )

    return (
        queryset.values(
            "employee__department__id",
            "employee__department__name",
        )
        .annotate(
            employee_count=Count("employee_id", distinct=True),
            total_days=Count("id"),
            present_days=Count("id", filter=Q(status=DailyAttendance.Status.PRESENT)),
            absent_days=Count("id", filter=Q(status=DailyAttendance.Status.ABSENT)),
            late_days=Count("id", filter=Q(status=DailyAttendance.Status.LATE)),
            total_late_minutes=Sum("late_minutes"),
            total_overtime_minutes=Sum("overtime_minutes"),
        )
        .order_by("employee__department__name")
    )
