from django.db.models import Q, QuerySet

from schedule.models import (
    ScheduleAssignment,
    Shift,
    TemporarySchedule,
    Timetable,
)


def timetable_list(*, search: str = "") -> QuerySet[Timetable]:
    queryset = Timetable.objects.order_by("name")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )

    return queryset


def shift_list(*, search: str = "") -> QuerySet[Shift]:
    queryset = (
        Shift.objects.prefetch_related("days")
        .order_by("name")
    )

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )

    return queryset


def schedule_assignment_list(*, search: str = "") -> QuerySet[ScheduleAssignment]:
    queryset = (
        ScheduleAssignment.objects.select_related("shift", "employee", "department")
        .order_by("-start_date")
    )

    if search:
        queryset = queryset.filter(
            Q(shift__name__icontains=search)
            | Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
            | Q(department__name__icontains=search)
        )

    return queryset


def temporary_schedule_list(*, search: str = "") -> QuerySet[TemporarySchedule]:
    queryset = (
        TemporarySchedule.objects.select_related("employee", "timetable")
        .order_by("-date")
    )

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
            | Q(timetable__name__icontains=search)
            | Q(reason__icontains=search)
        )

    return queryset
