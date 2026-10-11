from datetime import date, datetime, timedelta
from datetime import time as dt_time

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from schedule.models import (
    EmployeeScheduleAssignment,
    EmployeeScheduleOverride,
    Schedule,
    ScheduledShiftDay,
    Timetable,
    TimetableBreak,
)

TIMETABLE_TIMES_ORDER_ERROR = (
    "Check-out must be after check-in. For an overnight shift "
    "(e.g. 22:00 to 06:00), set check-out cross days to 1."
)

BREAK_OUTSIDE_WORK_ERROR = (
    "Break must be within working hours (check-in to check-out)."
)

__all__ = (
    "BREAK_OUTSIDE_WORK_ERROR",
    "TIMETABLE_TIMES_ORDER_ERROR",
    "build_timetable_snapshot",
    "default_day_change_time",
    "find_shift_for_punch",
    "get_or_materialize_shift",
    "validate_assignment",
    "validate_break_within_timetable",
    "validate_override",
    "validate_schedule",
    "validate_timetable",
    "validate_timetable_break",
    "validate_timetable_times",
)


def default_day_change_time(*, check_out_cross_days: int = 0) -> dt_time:
    """Boundary below which a punch belongs to the previous attendance day.

    A same-day shift starts and ends on one date, so midnight is the only
    sensible boundary: any earlier check-in simply stays on its own day.
    An overnight shift (check-out past midnight) instead needs a morning
    boundary, otherwise the early-morning checkout would be attributed to
    the day the shift ended rather than the one it started on.
    """
    return dt_time(8, 0) if check_out_cross_days else dt_time(0, 0)


def validate_timetable_times(
    *,
    check_in,
    check_out,
    check_out_cross_days,
) -> None:
    """
    Check-out must land strictly after check-in on the effective
    timeline (check-out offset by its cross-day value), so 22:00 ->
    06:00 is only valid with check_out_cross_days >= 1.

    Missing times or cross-day values are skipped here; field-level
    validation reports them.
    """
    if check_in is None or check_out is None:
        return
    if check_out_cross_days is None:
        return

    # Compare on a timeline anchored to one date, offset by the
    # cross-day field.
    anchor = date(2000, 1, 1)
    effective_in = datetime.combine(anchor, check_in)
    effective_out = datetime.combine(
        anchor + timedelta(days=check_out_cross_days),
        check_out,
    )
    if effective_out <= effective_in:
        raise ValidationError({"check_out_cross_days": TIMETABLE_TIMES_ORDER_ERROR})


def validate_break_within_timetable(
    *,
    start_time,
    end_time,
    check_in,
    check_out,
    check_out_cross_days: int = 0,
) -> None:
    """Break window must sit inside the timetable's work window.

    Overnight-aware: with ``check_out_cross_days >= 1`` the work window
    spans midnight, and early-morning breaks are read on the next day.
    Flexible timetables without fixed times are skipped (no window).
    """
    if start_time is None or end_time is None:
        return
    if check_in is None or check_out is None:
        return
    anchor = date(2000, 1, 1)
    work_start = datetime.combine(anchor, check_in)
    work_end = datetime.combine(
        anchor + timedelta(days=check_out_cross_days or 0),
        check_out,
    )
    break_start = datetime.combine(anchor, start_time)
    break_end = datetime.combine(anchor, end_time)
    if break_end <= break_start:
        return  # Reported separately as an ordering error.
    if (check_out_cross_days or 0) and break_start < work_start:
        break_start += timedelta(days=1)
        break_end += timedelta(days=1)
    if break_start < work_start or break_end > work_end:
        raise ValidationError({"start_time": BREAK_OUTSIDE_WORK_ERROR})


def validate_timetable(
    *,
    check_in=None,
    check_out=None,
    check_out_cross_days=0,
    type: str = Timetable.Type.NORMAL,
    work_minutes=None,
    day_change_time=None,
) -> None:
    """All timetable business rules (times order, flexible, day-change)."""
    validate_timetable_times(
        check_in=check_in,
        check_out=check_out,
        check_out_cross_days=check_out_cross_days,
    )
    if type == Timetable.Type.FLEXIBLE and work_minutes in (None, ""):
        raise ValidationError(
            {
                "work_minutes": (
                    "Required working minutes must be set for flexible timetables."
                )
            }
        )
    # Punches before day_change_time attribute to the previous day,
    # so a check-in punch earlier than it would land on the wrong day.
    if (
        check_in is not None
        and day_change_time is not None
        and day_change_time > check_in
    ):
        raise ValidationError(
            {
                "day_change_time": (
                    "Day change time must not be later than check-in; "
                    "punches before it count toward the previous day."
                )
            }
        )


def validate_timetable_break(
    *,
    start_time=None,
    end_time=None,
    break_time_type: str = TimetableBreak.BreakType.FIXED,
    break_time_minutes=None,
    check_in=None,
    check_out=None,
    check_out_cross_days: int = 0,
    validate_window: bool = False,
) -> None:
    """Break rules: ordering, flexible minutes, optional work-window."""
    if (
        start_time is not None
        and end_time is not None
        and end_time <= start_time
    ):
        raise ValidationError(
            {"end_time": "End time must be after start time."}
        )
    if (
        break_time_type == TimetableBreak.BreakType.FLEXIBLE
        and break_time_minutes is None
    ):
        raise ValidationError(
            {
                "break_time_minutes": (
                    "Break minutes are required for flexible breaks."
                )
            }
        )
    if validate_window:
        validate_break_within_timetable(
            start_time=start_time,
            end_time=end_time,
            check_in=check_in,
            check_out=check_out,
            check_out_cross_days=check_out_cross_days or 0,
        )


def validate_schedule(
    *,
    start_date=None,
    end_date=None,
    repeat: bool = True,
    repeat_every=1,
) -> None:
    if start_date and end_date and end_date < start_date:
        raise ValidationError({"end_date": "End date must not be before start date."})
    if repeat and repeat_every is not None and repeat_every < 1:
        raise ValidationError(
            {"repeat_every": "Repeat interval must be at least 1."}
        )


def validate_assignment(*, start_date=None, end_date=None) -> None:
    if start_date and end_date and end_date < start_date:
        raise ValidationError({"end_date": "End date must not be before start date."})


def validate_override(*, is_day_off: bool = False, schedule=None) -> None:
    schedule_id = getattr(schedule, "pk", schedule)
    if is_day_off and schedule_id:
        raise ValidationError(
            {
                "schedule": (
                    "A day-off override must not point at a schedule."
                )
            }
        )
    if not is_day_off and schedule_id is None:
        raise ValidationError(
            {
                "schedule": (
                    "Choose a schedule for the swap, or mark the day "
                    "as a day off."
                )
            }
        )


@transaction.atomic
def timetable_create(
    *,
    name: str,
    code: str | None = None,
    type: str = Timetable.Type.NORMAL,
    check_in=None,
    check_out=None,
    check_out_cross_days: int = 0,
    day_change_time=None,
    work_minutes=None,
    grace_period_check_out: bool = False,
    grace_period_minutes: int = 0,
    count_break_time_as_work_time: bool = False,
    multiple_in_out: bool = False,
    is_active: bool = True,
) -> Timetable:
    timetable = Timetable(
        name=name,
        code=code,
        type=type,
        check_in=check_in,
        check_out=check_out,
        check_out_cross_days=check_out_cross_days,
        work_minutes=work_minutes,
        grace_period_check_out=grace_period_check_out,
        grace_period_minutes=grace_period_minutes,
        count_break_time_as_work_time=count_break_time_as_work_time,
        multiple_in_out=multiple_in_out,
        is_active=is_active,
        day_change_time=(
            day_change_time
            if day_change_time is not None
            else default_day_change_time(
                check_out_cross_days=check_out_cross_days
            )
        ),
    )
    timetable.full_clean()
    validate_timetable(
        check_in=timetable.check_in,
        check_out=timetable.check_out,
        check_out_cross_days=timetable.check_out_cross_days,
        type=timetable.type,
        work_minutes=timetable.work_minutes,
        day_change_time=timetable.day_change_time,
    )
    timetable.save()
    return timetable


@transaction.atomic
def timetable_update(
    *,
    timetable: Timetable,
    name: str,
    code: str | None = None,
    type: str = Timetable.Type.NORMAL,
    check_in=None,
    check_out=None,
    check_out_cross_days: int = 0,
    day_change_time=None,
    work_minutes=None,
    grace_period_check_out: bool = False,
    grace_period_minutes: int = 0,
    count_break_time_as_work_time: bool = False,
    multiple_in_out: bool = False,
    is_active: bool = True,
) -> Timetable:
    timetable.name = name
    timetable.code = code
    timetable.type = type
    timetable.check_in = check_in
    timetable.check_out = check_out
    timetable.check_out_cross_days = check_out_cross_days
    timetable.day_change_time = (
        day_change_time
        if day_change_time is not None
        else default_day_change_time(check_out_cross_days=check_out_cross_days)
    )
    timetable.work_minutes = work_minutes
    timetable.grace_period_check_out = grace_period_check_out
    timetable.grace_period_minutes = grace_period_minutes
    timetable.count_break_time_as_work_time = count_break_time_as_work_time
    timetable.multiple_in_out = multiple_in_out
    timetable.is_active = is_active
    timetable.full_clean()
    validate_timetable(
        check_in=timetable.check_in,
        check_out=timetable.check_out,
        check_out_cross_days=timetable.check_out_cross_days,
        type=timetable.type,
        work_minutes=timetable.work_minutes,
        day_change_time=timetable.day_change_time,
    )
    timetable.save()
    return timetable


@transaction.atomic
def timetable_delete(*, timetable: Timetable) -> Timetable:
    """Deletes the timetable (cascades to its schedules)."""
    timetable.delete()
    return timetable


def _validate_timetable_break(
    break_: TimetableBreak, timetable: Timetable | None = None
) -> None:
    # Ordering and flexible-minutes rules plus work-window containment
    # against an explicitly supplied window (the formset passes fresh
    # parent values itself).
    timetable = timetable if timetable is not None else getattr(
        break_, "timetable", None
    )
    validate_timetable_break(
        start_time=break_.start_time,
        end_time=break_.end_time,
        break_time_type=break_.break_time_type,
        break_time_minutes=break_.break_time_minutes,
        check_in=getattr(timetable, "check_in", None),
        check_out=getattr(timetable, "check_out", None),
        check_out_cross_days=getattr(timetable, "check_out_cross_days", 0) or 0,
        validate_window=timetable is not None,
    )


@transaction.atomic
def timetable_break_create(
    *,
    timetable: Timetable,
    name: str,
    break_time_type: str = TimetableBreak.BreakType.FIXED,
    break_time_minutes=None,
    start_time=None,
    end_time=None,
) -> TimetableBreak:
    break_ = TimetableBreak(
        timetable=timetable,
        name=name,
        break_time_type=break_time_type,
        break_time_minutes=break_time_minutes,
        start_time=start_time,
        end_time=end_time,
    )
    break_.full_clean()
    _validate_timetable_break(break_, timetable)
    break_.save()
    return break_


@transaction.atomic
def timetable_break_update(
    *,
    break_: TimetableBreak,
    name: str,
    break_time_type: str = TimetableBreak.BreakType.FIXED,
    break_time_minutes=None,
    start_time=None,
    end_time=None,
) -> TimetableBreak:
    break_.name = name
    break_.break_time_type = break_time_type
    break_.break_time_minutes = break_time_minutes
    break_.start_time = start_time
    break_.end_time = end_time
    break_.full_clean()
    _validate_timetable_break(break_)
    break_.save()
    return break_


@transaction.atomic
def timetable_break_delete(*, break_: TimetableBreak) -> TimetableBreak:
    """Deletes the break."""
    break_.delete()
    return break_


@transaction.atomic
def schedule_create(
    *,
    name: str,
    timetable: Timetable,
    start_date=None,
    end_date=None,
    repeat: bool = True,
    repeat_every: int = 1,
    repeat_unit: str = Schedule.RepeatUnitType.WEEK,
) -> Schedule:
    schedule = Schedule(
        name=name,
        timetable=timetable,
        start_date=start_date,
        end_date=end_date,
        repeat=repeat,
        repeat_every=repeat_every,
        repeat_unit=repeat_unit,
    )
    schedule.full_clean()
    validate_schedule(
        start_date=schedule.start_date,
        end_date=schedule.end_date,
        repeat=schedule.repeat,
        repeat_every=schedule.repeat_every,
    )
    schedule.save()
    return schedule


@transaction.atomic
def schedule_update(
    *,
    schedule: Schedule,
    name: str,
    timetable: Timetable,
    start_date=None,
    end_date=None,
    repeat: bool = True,
    repeat_every: int = 1,
    repeat_unit: str = Schedule.RepeatUnitType.WEEK,
) -> Schedule:
    schedule.name = name
    schedule.timetable = timetable
    schedule.start_date = start_date
    schedule.end_date = end_date
    schedule.repeat = repeat
    schedule.repeat_every = repeat_every
    schedule.repeat_unit = repeat_unit
    schedule.full_clean()
    validate_schedule(
        start_date=schedule.start_date,
        end_date=schedule.end_date,
        repeat=schedule.repeat,
        repeat_every=schedule.repeat_every,
    )
    schedule.save()
    return schedule


@transaction.atomic
def schedule_delete(*, schedule: Schedule) -> Schedule:
    """Deletes the schedule."""
    schedule.delete()
    return schedule


# Assignment member resolution modes.
ASSIGNMENT_MODE_DEPARTMENT = "department"
ASSIGNMENT_MODE_INDIVIDUAL = "individual"
ASSIGNMENT_MODE_ALL_EXCEPT = "all_except"

ASSIGNMENT_MODES = (
    (ASSIGNMENT_MODE_DEPARTMENT, "By department"),
    (ASSIGNMENT_MODE_INDIVIDUAL, "Person by person"),
    (ASSIGNMENT_MODE_ALL_EXCEPT, "Everyone except…"),
)


def resolve_assignment_employees(
    *,
    mode: str,
    departments=None,
    employees=None,
    excluded=None,
):
    """Resolve the employee set for a schedule assignment.

    - ``department``: all active employees in the given departments.
    - ``individual``: exactly the given employees (active only).
    - ``all_except``: all active employees minus ``excluded``.
    Returns a list of active ``Employee`` objects, ordered by name.
    """
    from employees.models import Employee

    base = Employee.objects.filter(is_active=True).order_by(
        "first_name", "last_name"
    )
    if mode == ASSIGNMENT_MODE_DEPARTMENT:
        department_ids = [
            getattr(department, "pk", department) for department in (departments or [])
        ]
        return list(base.filter(department_id__in=department_ids))
    if mode == ASSIGNMENT_MODE_ALL_EXCEPT:
        excluded_ids = [
            getattr(employee, "pk", employee) for employee in (excluded or [])
        ]
        return list(base.exclude(pk__in=excluded_ids))
    employee_ids = [
        getattr(employee, "pk", employee) for employee in (employees or [])
    ]
    return list(base.filter(pk__in=employee_ids))


@transaction.atomic
def assignment_create(
    *,
    schedule: Schedule,
    employees,
    start_date,
    end_date=None,
    priority: int = 0,
    name: str = "",
    is_active: bool = True,
) -> EmployeeScheduleAssignment:
    """Create an assignment row covering ``employees`` over a date range."""
    assignment = EmployeeScheduleAssignment(
        schedule=schedule,
        start_date=start_date,
        end_date=end_date,
        priority=priority,
        name=name,
        is_active=is_active,
    )
    assignment.full_clean()
    validate_assignment(
        start_date=assignment.start_date,
        end_date=assignment.end_date,
    )
    assignment.save()
    if employees:
        assignment.employees.add(*employees)
    return assignment


@transaction.atomic
def assignment_delete(
    *, assignment: EmployeeScheduleAssignment
) -> EmployeeScheduleAssignment:
    """Deletes the assignment."""
    assignment.delete()
    return assignment


@transaction.atomic
def override_create(
    *,
    employee,
    date,
    schedule: Schedule | None = None,
    is_day_off: bool = False,
    reason: str = "",
) -> EmployeeScheduleOverride:
    """Create a one-day override (day-off or schedule swap)."""
    override = EmployeeScheduleOverride(
        employee=employee,
        date=date,
        schedule=schedule,
        is_day_off=is_day_off,
        reason=reason,
    )
    override.full_clean()
    validate_override(is_day_off=override.is_day_off, schedule=override.schedule)
    override.save()
    return override


@transaction.atomic
def override_update(
    *,
    override: EmployeeScheduleOverride,
    schedule: Schedule | None = None,
    is_day_off: bool = False,
    reason: str = "",
) -> EmployeeScheduleOverride:
    override.schedule = schedule
    override.is_day_off = is_day_off
    override.reason = reason
    override.full_clean()
    validate_override(is_day_off=override.is_day_off, schedule=override.schedule)
    override.save()
    return override


@transaction.atomic
def override_delete(
    *, override: EmployeeScheduleOverride
) -> EmployeeScheduleOverride:
    """Deletes the override."""
    override.delete()
    return override


# --------------------------------------------------------------------------
# Shift-day materialization — the single writer of the daily plan.
# --------------------------------------------------------------------------

#: Punch-attribution margins around a shift. A punch in
#: ``[shift_start - EARLY, shift_end + LATE)`` belongs to the row.
SHIFT_WINDOW_EARLY_MARGIN = timedelta(hours=4)
SHIFT_WINDOW_LATE_MARGIN = timedelta(hours=8)


def build_timetable_snapshot(*, timetable: Timetable) -> dict | None:
    """Freeze the timetable params a shift row's numbers were computed from.

    Editing or deleting the timetable later must not rewrite history,
    so the calculator reads this snapshot, never the live timetable.
    """
    if timetable is None:
        return None
    return {
        "timetable_id": timetable.pk,
        "name": timetable.name,
        "check_in": timetable.check_in.isoformat() if timetable.check_in else None,
        "check_out": timetable.check_out.isoformat() if timetable.check_out else None,
        "check_out_cross_days": timetable.check_out_cross_days or 0,
        "grace_period_minutes": timetable.grace_period_minutes or 0,
        "grace_period_check_out": bool(timetable.grace_period_check_out),
        "duplicate_punch_window_minutes": timetable.duplicate_punch_window_minutes,
        "multiple_in_out": bool(timetable.multiple_in_out),
        "count_break_time_as_work_time": bool(
            timetable.count_break_time_as_work_time
        ),
        "breaks": [
            {
                "start_time": b.start_time.isoformat(),
                "end_time": b.end_time.isoformat(),
                "break_time_type": b.break_time_type,
                "break_time_minutes": b.break_time_minutes,
            }
            for b in timetable.breaks.all()
        ],
    }


def _shift_datetimes(
    *, timetable: Timetable, day: date
) -> tuple[datetime, datetime] | tuple[None, None]:
    """Absolute (aware) shift start/end for ``timetable`` on ``day``.

    Returns (None, None) when the timetable has no fixed times.
    """
    if timetable.check_in is None or timetable.check_out is None:
        return None, None
    start = timezone.make_aware(datetime.combine(day, timetable.check_in))
    end = timezone.make_aware(
        datetime.combine(
            day + timedelta(days=timetable.check_out_cross_days or 0),
            timetable.check_out,
        )
    )
    return start, end


def _shift_windows(
    *, start: datetime, end: datetime
) -> tuple[datetime, datetime]:
    """Attribution window for a shift: margins for early/late punches."""
    return start - SHIFT_WINDOW_EARLY_MARGIN, end + SHIFT_WINDOW_LATE_MARGIN


def _assert_no_window_overlap(*, employee, window_start, window_end, day) -> None:
    """Loud failure beats silent corruption: windows must not overlap."""
    clash = (
        ScheduledShiftDay.objects.filter(
            employee=employee,
            window_start__lt=window_end,
            window_end__gt=window_start,
        )
        .exclude(day=day)
        .first()
    )
    if clash is not None:
        raise ValidationError(
            {
                "window_start": (
                    f"Shift window overlaps {clash.day} "
                    f"({clash.window_start} -> {clash.window_end})."
                )
            }
        )


def _create_shift_row(
    *,
    employee,
    day: date,
    day_type: str,
    source: str,
    timetable=None,
    assignment=None,
    override=None,
) -> ScheduledShiftDay:
    shift_start = shift_end = window_start = window_end = None
    if timetable is not None:
        shift_start, shift_end = _shift_datetimes(timetable=timetable, day=day)
    if shift_start is not None and shift_end is not None:
        window_start, window_end = _shift_windows(start=shift_start, end=shift_end)
        _assert_no_window_overlap(
            employee=employee,
            window_start=window_start,
            window_end=window_end,
            day=day,
        )
    return ScheduledShiftDay.objects.create(
        employee=employee,
        day=day,
        day_type=day_type,
        timetable=timetable,
        shift_start=shift_start,
        shift_end=shift_end,
        window_start=window_start,
        window_end=window_end,
        timetable_snapshot=build_timetable_snapshot(timetable=timetable),
        source=source,
        assignment=assignment,
        override=override,
    )


def _holiday_on(*, day: date):
    """Active holiday covering ``day``, if any.

    A NULL ``end_date`` means a one-day holiday (unlike assignments,
    where NULL means open-ended).
    """
    from django.db.models import Q

    from leave.models import Holiday

    return (
        Holiday.objects.filter(is_active=True)
        .filter(Q(date=day) | Q(date__lte=day, end_date__gte=day))
        .order_by("date")
        .first()
    )


def _resolve_shift_timetable(*, schedule: Schedule, day: date):
    """The timetable working ``schedule`` on ``day``.

    The schedule entry for the weekday wins; the schedule's own
    timetable is the fallback (entry-less schedules behave exactly
    like the old assignment → timetable resolution).
    """
    candidates = []
    entry = (
        schedule.entries.filter(day_index=day.weekday())
        .select_related("timetable")
        .first()
    )
    if entry is not None and entry.timetable is not None:
        candidates.append(entry.timetable)
    if schedule.timetable is not None:
        candidates.append(schedule.timetable)
    for timetable in candidates:
        if timetable.check_in is not None and timetable.check_out is not None:
            return timetable
    return None


def get_or_materialize_shift(*, employee, day: date) -> ScheduledShiftDay | None:
    """Return the (employee, day) plan row, creating it when coverage exists.

    Precedence: day-off override, swap override, holiday, then the
    highest-priority assignment covering the day. Returns a
    ``(shift_or_None, created)`` tuple; ``created`` is False when the row
    already existed. Never touches a row that already exists.
    """
    from schedule.selectors import assignment_list, schedule_is_active_on

    existing = ScheduledShiftDay.objects.filter(employee=employee, day=day).first()
    if existing is not None:
        return existing, False

    override = (
        EmployeeScheduleOverride.objects.filter(employee=employee, date=day).first()
    )
    if override is not None:
        if override.is_day_off:
            return _create_shift_row(
                employee=employee,
                day=day,
                day_type=ScheduledShiftDay.DayType.DAY_OFF,
                source=ScheduledShiftDay.Source.OVERRIDE,
                override=override,
            ), True
        if override.schedule is not None:
            timetable = _resolve_shift_timetable(schedule=override.schedule, day=day)
            if timetable is None:
                return None, False
            return _create_shift_row(
                employee=employee,
                day=day,
                day_type=ScheduledShiftDay.DayType.WORKING,
                source=ScheduledShiftDay.Source.OVERRIDE,
                timetable=timetable,
                override=override,
            ), True
        return None, False

    if _holiday_on(day=day) is not None:
        return _create_shift_row(
            employee=employee,
            day=day,
            day_type=ScheduledShiftDay.DayType.HOLIDAY,
            source=ScheduledShiftDay.Source.HOLIDAY,
        ), True

    assignments = (
        assignment_list(employee=employee, day=day)
        .filter(schedule__is_active=True)
        .order_by("-priority", "-start_date")
    )
    for assignment in assignments:
        schedule_obj = assignment.schedule
        if not schedule_is_active_on(schedule=schedule_obj, day=day):
            continue
        timetable = _resolve_shift_timetable(schedule=schedule_obj, day=day)
        if timetable is None:
            continue
        return _create_shift_row(
            employee=employee,
            day=day,
            day_type=ScheduledShiftDay.DayType.WORKING,
            source=ScheduledShiftDay.Source.ASSIGNMENT,
            timetable=timetable,
            assignment=assignment,
        ), True
    return None, False


def find_shift_for_punch(*, employee, timestamp) -> ScheduledShiftDay | None:
    """The shift row whose attribution window contains ``timestamp``.

    Overlapping windows (should not happen — see the write guard) resolve
    to the most recently starting row. Returns None when unlinked.
    """
    ts = timestamp
    if timezone.is_naive(ts):
        ts = timezone.make_aware(ts)
    return (
        ScheduledShiftDay.objects.filter(
            employee=employee,
            window_start__lte=ts,
            window_end__gt=ts,
        )
        .order_by("-window_start")
        .first()
    )
