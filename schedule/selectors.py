from dataclasses import dataclass
from datetime import date

from django.db.models import Q, QuerySet

from schedule.models import (
    EmployeeScheduleAssignment,
    EmployeeScheduleOverride,
    Schedule,
    Timetable,
    TimetableBreak,
)


def timetable_list(*, search: str = "") -> QuerySet[Timetable]:
    queryset = Timetable.objects.prefetch_related("breaks").order_by("name")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )

    return queryset


def timetable_break_list(
    *, timetable: Timetable | None = None, search: str = ""
) -> QuerySet[TimetableBreak]:
    queryset = TimetableBreak.objects.select_related("timetable").order_by(
        "start_time", "name"
    )

    if timetable is not None:
        queryset = queryset.filter(timetable=timetable)

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(timetable__name__icontains=search)
        )

    return queryset


def schedule_list(*, search: str = "") -> QuerySet[Schedule]:
    queryset = Schedule.objects.select_related("timetable").order_by("name")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(timetable__name__icontains=search)
        )

    return queryset


@dataclass(frozen=True)
class ResolvedSchedule:
    """Schedule resolution for one (employee, day).

    `is_day_off` True means an override marked the day off (schedule and
    timetable are None). Both None with `is_day_off` False means no
    schedule covers the day.
    """

    schedule: Schedule | None
    timetable: Timetable | None
    is_day_off: bool = False


def schedule_is_active_on(*, schedule: Schedule, day: date) -> bool:
    """True when `schedule` covers `day` per its window + repeat rule."""
    if not schedule.is_active:
        return False
    if schedule.start_date and day < schedule.start_date:
        return False
    if schedule.end_date and day > schedule.end_date:
        return False
    if not schedule.repeat:
        return True
    anchor = schedule.start_date
    if anchor is None or day < anchor:
        return anchor is None
    every = max(schedule.repeat_every or 1, 1)
    if schedule.repeat_unit == Schedule.RepeatUnitType.WEEK:
        return ((day - anchor).days // 7) % every == 0
    if schedule.repeat_unit == Schedule.RepeatUnitType.MONTH:
        months = (day.year - anchor.year) * 12 + (day.month - anchor.month)
        return months % every == 0
    if schedule.repeat_unit == Schedule.RepeatUnitType.YEAR:
        return (day.year - anchor.year) % every == 0
    return True


def _usable(*, schedule: Schedule) -> Timetable | None:
    timetable = schedule.timetable
    if timetable is None or not timetable.is_active:
        return None
    return timetable


def resolve_schedule_for_employee_on_date(
    *, employee, day: date
) -> ResolvedSchedule:
    """Resolve which schedule/timetable applies to `employee` on `day`.

    Precedence: one-day override wins, then the active assignment with the
    highest priority covering the day (most recent start_date breaks ties).
    """
    override = (
        EmployeeScheduleOverride.objects.select_related("schedule__timetable")
        .filter(employee=employee, date=day)
        .first()
    )
    if override is not None:
        if override.is_day_off:
            return ResolvedSchedule(
                schedule=None, timetable=None, is_day_off=True
            )
        if override.schedule is not None:
            timetable = _usable(schedule=override.schedule)
            if timetable is not None:
                return ResolvedSchedule(
                    schedule=override.schedule, timetable=timetable
                )

    assignment = (
        EmployeeScheduleAssignment.objects.select_related(
            "schedule__timetable"
        )
        .filter(
            employees=employee,
            is_active=True,
            start_date__lte=day,
        )
        .filter(Q(end_date__gte=day) | Q(end_date__isnull=True))
        .filter(schedule__is_active=True)
        .order_by("-priority", "-start_date")
        .first()
    )
    if assignment is not None and schedule_is_active_on(
        schedule=assignment.schedule, day=day
    ):
        timetable = _usable(schedule=assignment.schedule)
        if timetable is not None:
            return ResolvedSchedule(
                schedule=assignment.schedule, timetable=timetable
            )

    return ResolvedSchedule(schedule=None, timetable=None)


def timetable_for_employee_on_date(*, employee, day: date) -> Timetable | None:
    """Convenience wrapper returning just the timetable (None on day-off)."""
    return resolve_schedule_for_employee_on_date(
        employee=employee, day=day
    ).timetable
