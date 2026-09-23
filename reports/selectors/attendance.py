from datetime import date

from django.db.models import Count, Q, QuerySet, Sum

from attendance.models import Attendance


def _attendance_base_queryset(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
) -> QuerySet[Attendance]:
    queryset = Attendance.objects.filter(
        day__range=(date_from, date_to),
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
        _attendance_base_queryset(
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
            present_days=Count("id", filter=Q(status=Attendance.Status.PRESENT)),
            absent_days=Count("id", filter=Q(status=Attendance.Status.ABSENT)),
            late_days=Count("id", filter=Q(status=Attendance.Status.LATE)),
            leave_days=Count("id", filter=Q(status=Attendance.Status.LEAVE)),
            total_worked=Sum("total_work_time"),
            total_late=Sum("late_time"),
            total_overtime=Sum("over_time"),
        )
        .order_by("employee__first_name", "employee__last_name")
    )


def individual_attendance_list(
    *,
    date_from: date,
    date_to: date,
    employee_id: int,
):
    return (
        _attendance_base_queryset(
            date_from=date_from,
            date_to=date_to,
            employee_id=employee_id,
        )
        .select_related("shift")
        .prefetch_related("attendance_activities")
        .order_by("day")
    )


def department_attendance_list(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
):
    queryset = _attendance_base_queryset(
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
            present_days=Count("id", filter=Q(status=Attendance.Status.PRESENT)),
            absent_days=Count("id", filter=Q(status=Attendance.Status.ABSENT)),
            late_days=Count("id", filter=Q(status=Attendance.Status.LATE)),
            total_late=Sum("late_time"),
            total_overtime=Sum("over_time"),
        )
        .order_by("employee__department__name")
    )
