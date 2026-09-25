from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from schedule.models import Schedule, Timetable, TimetableBreak

TIMETABLE_TIMES_ORDER_ERROR = (
    "Check-out must be after check-in. For an overnight shift "
    "(e.g. 22:00 to 06:00), set check-out cross days to 1."
)


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


@transaction.atomic
def timetable_create(
    *,
    name: str,
    code: str | None = None,
    type: str = Timetable.Type.NORMAL,
    check_in=None,
    check_out=None,
    check_out_cross_days: int = 0,
    work_minutes=None,
    check_in_start=None,
    check_in_end=None,
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
        check_in_start=check_in_start,
        check_in_end=check_in_end,
        grace_period_check_out=grace_period_check_out,
        grace_period_minutes=grace_period_minutes,
        count_break_time_as_work_time=count_break_time_as_work_time,
        multiple_in_out=multiple_in_out,
        is_active=is_active,
    )
    timetable.full_clean()
    validate_timetable_times(
        check_in=timetable.check_in,
        check_out=timetable.check_out,
        check_out_cross_days=timetable.check_out_cross_days,
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
    work_minutes=None,
    check_in_start=None,
    check_in_end=None,
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
    timetable.work_minutes = work_minutes
    timetable.check_in_start = check_in_start
    timetable.check_in_end = check_in_end
    timetable.grace_period_check_out = grace_period_check_out
    timetable.grace_period_minutes = grace_period_minutes
    timetable.count_break_time_as_work_time = count_break_time_as_work_time
    timetable.multiple_in_out = multiple_in_out
    timetable.is_active = is_active
    timetable.full_clean()
    validate_timetable_times(
        check_in=timetable.check_in,
        check_out=timetable.check_out,
        check_out_cross_days=timetable.check_out_cross_days,
    )
    timetable.save()
    return timetable


@transaction.atomic
def timetable_delete(*, timetable: Timetable) -> Timetable:
    """Soft-deletes the timetable (recoverable via all_objects)."""
    timetable.delete()
    return timetable


BREAK_OUTSIDE_WORK_ERROR = (
    "Break must be within working hours (check-in to check-out)."
)


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


def _validate_timetable_break(
    break_: TimetableBreak, timetable: Timetable | None = None
) -> None:
    if (
        break_.start_time is not None
        and break_.end_time is not None
        and break_.end_time <= break_.start_time
    ):
        raise ValidationError({"end_time": "End time must be after start time."})
    if (
        break_.break_time_type == TimetableBreak.BreakType.FLEXIBLE
        and break_.break_time_minutes is None
    ):
        raise ValidationError(
            {"break_time_minutes": "Break minutes are required for flexible breaks."}
        )
    timetable = timetable if timetable is not None else getattr(
        break_, "timetable", None
    )
    if timetable is not None:
        validate_break_within_timetable(
            start_time=break_.start_time,
            end_time=break_.end_time,
            check_in=getattr(timetable, "check_in", None),
            check_out=getattr(timetable, "check_out", None),
            check_out_cross_days=getattr(timetable, "check_out_cross_days", 0) or 0,
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
    grace_period_check_out: bool = False,
    grace_period_minutes: int = 0,
) -> TimetableBreak:
    break_ = TimetableBreak(
        timetable=timetable,
        name=name,
        break_time_type=break_time_type,
        break_time_minutes=break_time_minutes,
        start_time=start_time,
        end_time=end_time,
        grace_period_check_out=grace_period_check_out,
        grace_period_minutes=grace_period_minutes,
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
    grace_period_check_out: bool = False,
    grace_period_minutes: int = 0,
) -> TimetableBreak:
    break_.name = name
    break_.break_time_type = break_time_type
    break_.break_time_minutes = break_time_minutes
    break_.start_time = start_time
    break_.end_time = end_time
    break_.grace_period_check_out = grace_period_check_out
    break_.grace_period_minutes = grace_period_minutes
    break_.full_clean()
    _validate_timetable_break(break_)
    break_.save()
    return break_


@transaction.atomic
def timetable_break_delete(*, break_: TimetableBreak) -> TimetableBreak:
    """Soft-deletes the break (recoverable via all_objects)."""
    break_.delete()
    return break_


def _validate_schedule(schedule: Schedule) -> None:
    if schedule.repeat and (schedule.repeat_every is None or schedule.repeat_every < 1):
        raise ValidationError({"repeat_every": "Repeat interval must be at least 1."})


@transaction.atomic
def schedule_create(
    *,
    name: str,
    timetable: Timetable,
    repeat: bool = True,
    repeat_every: int = 1,
    repeat_unit: str = Schedule.RepeatUnitType.WEEK,
) -> Schedule:
    schedule = Schedule(
        name=name,
        timetable=timetable,
        repeat=repeat,
        repeat_every=repeat_every,
        repeat_unit=repeat_unit,
    )
    schedule.full_clean()
    _validate_schedule(schedule)
    schedule.save()
    return schedule


@transaction.atomic
def schedule_update(
    *,
    schedule: Schedule,
    name: str,
    timetable: Timetable,
    repeat: bool = True,
    repeat_every: int = 1,
    repeat_unit: str = Schedule.RepeatUnitType.WEEK,
) -> Schedule:
    schedule.name = name
    schedule.timetable = timetable
    schedule.repeat = repeat
    schedule.repeat_every = repeat_every
    schedule.repeat_unit = repeat_unit
    schedule.full_clean()
    _validate_schedule(schedule)
    schedule.save()
    return schedule


@transaction.atomic
def schedule_delete(*, schedule: Schedule) -> Schedule:
    """Soft-deletes the schedule (recoverable via all_objects)."""
    schedule.delete()
    return schedule
