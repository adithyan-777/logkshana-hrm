from datetime import date

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
    queryset = Shift.objects.prefetch_related("days").order_by("name")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )

    return queryset


def schedule_assignment_list(*, search: str = "") -> QuerySet[ScheduleAssignment]:
    queryset = ScheduleAssignment.objects.select_related(
        "shift", "employee", "department"
    ).order_by("-start_date")

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
    queryset = TemporarySchedule.objects.select_related(
        "employee", "timetable"
    ).order_by("-date")

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
            | Q(timetable__name__icontains=search)
            | Q(reason__icontains=search)
        )

    return queryset


def timetable_for_employee_on_date(
    *,
    employee,
    day: date,
) -> Timetable | None:
    """
    Resolve the timetable that applies to an employee on a calendar date.

    Resolution order:
    1. A TemporarySchedule for the employee on that date that overrides
       the normal schedule.
    2. The newest ScheduleAssignment covering the date: employee-type
       assignments win over department-type, and on overlap the latest
       start_date wins. The assignment's Shift cycle picks the ShiftDay
       timetable for the date.
    3. None when nothing applies (unassigned, or the cycle position has
       no ShiftDay = day off).

    Cycle position: a weekly shift with cycle_count=1 uses the ISO
    weekday (Mon=1..Sun=7); every other cycle uses
    ((day - start_date).days % highest day_number) + 1.
    """
    temporary = TemporarySchedule.objects.filter(
        employee=employee,
        date=day,
        overrides_normal_schedule=True,
    ).first()
    if temporary is not None:
        return temporary.timetable

    assignment = _assignment_for_day(employee=employee, day=day)
    if assignment is None:
        return None

    return _timetable_for_shift_day(
        shift=assignment.shift,
        start_date=assignment.start_date,
        day=day,
    )


def _assignment_for_day(*, employee, day: date) -> ScheduleAssignment | None:
    assignment = (
        ScheduleAssignment.objects.filter(
            assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
            employee=employee,
            start_date__lte=day,
            end_date__gte=day,
        )
        .select_related("shift")
        .order_by("-start_date", "-id")
        .first()
    )
    if assignment is not None:
        return assignment

    if employee.department_id is None:
        return None

    return (
        ScheduleAssignment.objects.filter(
            assignment_type=ScheduleAssignment.AssignmentType.DEPARTMENT,
            department_id=employee.department_id,
            start_date__lte=day,
            end_date__gte=day,
        )
        .select_related("shift")
        .order_by("-start_date", "-id")
        .first()
    )


def _timetable_for_shift_day(*, shift: Shift, start_date: date, day: date) -> Timetable | None:
    shift_days = list(shift.days.all())
    if not shift_days:
        return None

    if shift.cycle_unit == Shift.CycleUnit.WEEK and shift.cycle_count == 1:
        position = day.isoweekday()
    else:
        cycle_length = max(shift_day.day_number for shift_day in shift_days)
        position = (day - start_date).days % cycle_length + 1

    for shift_day in shift_days:
        if shift_day.day_number == position:
            return shift_day.timetable
    return None
