from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from schedule.models import (
    ScheduleAssignment,
    Shift,
    ShiftDay,
    TemporarySchedule,
    Timetable,
)

TIMETABLE_TIMES_ORDER_ERROR = (
    "Check-out must be after check-in. For an overnight shift "
    "(e.g. 22:00 to 06:00), set check-out cross days to 1."
)


def validate_timetable_times(
    *,
    check_in,
    check_out,
    check_in_cross_days,
    check_out_cross_days,
) -> None:
    """
    Check-out must land strictly after check-in on the effective
    timeline (each time offset by its cross-day value), so 22:00 ->
    06:00 is only valid with check_out_cross_days >= 1.

    Missing times or cross-day values are skipped here; field-level
    validation reports them.
    """
    if check_in is None or check_out is None:
        return
    if check_in_cross_days is None or check_out_cross_days is None:
        return

    # Compare on a timeline anchored to one date, offset by the
    # cross-day fields.
    anchor = date(2000, 1, 1)
    effective_in = datetime.combine(
        anchor + timedelta(days=check_in_cross_days),
        check_in,
    )
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
    code: str,
    type: str,
    work_type: str,
    workday=1,
    check_in=None,
    check_out=None,
    work_minutes=None,
    check_in_start=None,
    check_in_end=None,
    check_out_start=None,
    check_out_end=None,
    check_in_cross_days: int = 0,
    check_out_cross_days: int = 0,
    require_check_in: bool = True,
    require_check_out: bool = True,
    allow_late_in: bool = False,
    allow_early_out: bool = False,
    late_in_grace_minutes: int = 0,
    early_out_grace_minutes: int = 0,
    multiple_in_out: bool = False,
    day_change_time=None,
    color: str = "",
    is_active: bool = True,
) -> Timetable:
    timetable = Timetable(
        name=name,
        code=code,
        type=type,
        work_type=work_type,
        workday=workday,
        check_in=check_in,
        check_out=check_out,
        work_minutes=work_minutes,
        check_in_start=check_in_start,
        check_in_end=check_in_end,
        check_out_start=check_out_start,
        check_out_end=check_out_end,
        check_in_cross_days=check_in_cross_days,
        check_out_cross_days=check_out_cross_days,
        require_check_in=require_check_in,
        require_check_out=require_check_out,
        allow_late_in=allow_late_in,
        allow_early_out=allow_early_out,
        late_in_grace_minutes=late_in_grace_minutes,
        early_out_grace_minutes=early_out_grace_minutes,
        multiple_in_out=multiple_in_out,
        day_change_time=day_change_time or "08:00",
        color=color,
        is_active=is_active,
    )
    timetable.full_clean()
    validate_timetable_times(
        check_in=timetable.check_in,
        check_out=timetable.check_out,
        check_in_cross_days=timetable.check_in_cross_days,
        check_out_cross_days=timetable.check_out_cross_days,
    )
    timetable.save()
    return timetable


@transaction.atomic
def timetable_update(
    *,
    timetable: Timetable,
    name: str,
    code: str,
    type: str,
    work_type: str,
    workday=1,
    check_in=None,
    check_out=None,
    work_minutes=None,
    check_in_start=None,
    check_in_end=None,
    check_out_start=None,
    check_out_end=None,
    check_in_cross_days: int = 0,
    check_out_cross_days: int = 0,
    require_check_in: bool = True,
    require_check_out: bool = True,
    allow_late_in: bool = False,
    allow_early_out: bool = False,
    late_in_grace_minutes: int = 0,
    early_out_grace_minutes: int = 0,
    multiple_in_out: bool = False,
    day_change_time=None,
    color: str = "",
    is_active: bool = True,
) -> Timetable:
    timetable.name = name
    timetable.code = code
    timetable.type = type
    timetable.work_type = work_type
    timetable.workday = workday
    timetable.check_in = check_in
    timetable.check_out = check_out
    timetable.work_minutes = work_minutes
    timetable.check_in_start = check_in_start
    timetable.check_in_end = check_in_end
    timetable.check_out_start = check_out_start
    timetable.check_out_end = check_out_end
    timetable.check_in_cross_days = check_in_cross_days
    timetable.check_out_cross_days = check_out_cross_days
    timetable.require_check_in = require_check_in
    timetable.require_check_out = require_check_out
    timetable.allow_late_in = allow_late_in
    timetable.allow_early_out = allow_early_out
    timetable.late_in_grace_minutes = late_in_grace_minutes
    timetable.early_out_grace_minutes = early_out_grace_minutes
    timetable.multiple_in_out = multiple_in_out
    timetable.day_change_time = day_change_time or "08:00"
    timetable.color = color
    timetable.is_active = is_active
    timetable.full_clean()
    validate_timetable_times(
        check_in=timetable.check_in,
        check_out=timetable.check_out,
        check_in_cross_days=timetable.check_in_cross_days,
        check_out_cross_days=timetable.check_out_cross_days,
    )
    timetable.save()
    return timetable


@transaction.atomic
def timetable_delete(*, timetable: Timetable) -> Timetable:
    """Soft-deletes the timetable (recoverable via all_objects)."""
    timetable.delete()
    return timetable


@transaction.atomic
def shift_create(
    *,
    name: str,
    code: str,
    auto_shift: bool = False,
    cycle_unit: str,
    cycle_count: int = 1,
    is_active: bool = True,
    shift_days: list[dict] | None = None,
) -> Shift:
    shift = Shift(
        name=name,
        code=code,
        auto_shift=auto_shift,
        cycle_unit=cycle_unit,
        cycle_count=cycle_count,
        is_active=is_active,
    )
    shift.full_clean()
    shift.save()

    for day_data in shift_days or []:
        shift_day = ShiftDay(shift=shift, **day_data)
        shift_day.full_clean()
        shift_day.save()

    return shift


@transaction.atomic
def shift_update(
    *,
    shift: Shift,
    name: str,
    code: str,
    auto_shift: bool = False,
    cycle_unit: str,
    cycle_count: int = 1,
    is_active: bool = True,
    shift_days: list[dict] | None = None,
) -> Shift:
    shift.name = name
    shift.code = code
    shift.auto_shift = auto_shift
    shift.cycle_unit = cycle_unit
    shift.cycle_count = cycle_count
    shift.is_active = is_active
    shift.full_clean()
    shift.save()

    # Replace the day set to mirror shift_create semantics. Rows are
    # matched by day_number so the (shift, day_number) unique
    # constraint — which also covers soft-deleted rows — is never
    # violated: reused days are updated in place, removed days are
    # soft-deleted via .delete(), and brand-new days are created.
    new_days = list(shift_days or [])
    day_numbers = [day_data["day_number"] for day_data in new_days]
    if len(set(day_numbers)) != len(day_numbers):
        raise ValidationError("Duplicate day number in shift days.")
    existing = {day.day_number: day for day in shift.days.all()}
    seen: set[int] = set()
    for day_data in new_days:
        day_number = day_data["day_number"]
        seen.add(day_number)
        if day_number in existing:
            row = existing[day_number]
            row.timetable = day_data["timetable"]
            row.full_clean()
            row.save()
        else:
            row = ShiftDay(shift=shift, **day_data)
            row.full_clean()
            row.save()
    for day_number, row in existing.items():
        if day_number not in seen:
            row.delete()

    return shift


@transaction.atomic
def shift_delete(*, shift: Shift) -> Shift:
    """Soft-deletes the shift and its day rows (recoverable via all_objects)."""
    for day in shift.days.all():
        day.delete()
    shift.delete()
    return shift


@transaction.atomic
def schedule_assignment_create(
    *,
    assignment_type: str,
    shift: Shift,
    start_date,
    end_date,
    employee=None,
    department=None,
    overwrite_existing: bool = False,
) -> ScheduleAssignment:
    assignment = ScheduleAssignment(
        assignment_type=assignment_type,
        shift=shift,
        start_date=start_date,
        end_date=end_date,
        employee=employee,
        department=department,
        overwrite_existing=overwrite_existing,
    )
    assignment.full_clean()
    _validate_schedule_assignment(assignment)
    assignment.save()
    return assignment


@transaction.atomic
def schedule_assignment_update(
    *,
    assignment: ScheduleAssignment,
    assignment_type: str,
    shift: Shift,
    start_date,
    end_date,
    employee=None,
    department=None,
    overwrite_existing: bool = False,
) -> ScheduleAssignment:
    assignment.assignment_type = assignment_type
    assignment.shift = shift
    assignment.start_date = start_date
    assignment.end_date = end_date
    assignment.employee = employee
    assignment.department = department
    assignment.overwrite_existing = overwrite_existing
    assignment.full_clean()
    _validate_schedule_assignment(assignment)
    assignment.save()
    return assignment


@transaction.atomic
def schedule_assignment_delete(*, assignment: ScheduleAssignment) -> ScheduleAssignment:
    """Soft-deletes the assignment (recoverable via all_objects)."""
    assignment.delete()
    return assignment


@transaction.atomic
def temporary_schedule_create(
    *,
    employee,
    date,
    timetable: Timetable,
    reason: str = "",
    overrides_normal_schedule: bool = True,
) -> TemporarySchedule:
    temporary = TemporarySchedule(
        employee=employee,
        date=date,
        timetable=timetable,
        reason=reason,
        overrides_normal_schedule=overrides_normal_schedule,
    )
    temporary.full_clean()
    temporary.save()
    return temporary


@transaction.atomic
def temporary_schedule_update(
    *,
    temporary: TemporarySchedule,
    employee,
    date,
    timetable: Timetable,
    reason: str = "",
    overrides_normal_schedule: bool = True,
) -> TemporarySchedule:
    temporary.employee = employee
    temporary.date = date
    temporary.timetable = timetable
    temporary.reason = reason
    temporary.overrides_normal_schedule = overrides_normal_schedule
    temporary.full_clean()
    temporary.save()
    return temporary


@transaction.atomic
def temporary_schedule_delete(*, temporary: TemporarySchedule) -> TemporarySchedule:
    """Soft-deletes the temporary schedule (recoverable via all_objects)."""
    temporary.delete()
    return temporary


def _validate_schedule_assignment(assignment: ScheduleAssignment) -> None:
    if assignment.end_date < assignment.start_date:
        raise ValidationError("End date must be on or after start date.")

    if assignment.assignment_type == ScheduleAssignment.AssignmentType.EMPLOYEE:
        if not assignment.employee:
            raise ValidationError("Employee is required for employee assignments.")
        assignment.department = None
    elif assignment.assignment_type == ScheduleAssignment.AssignmentType.DEPARTMENT:
        if not assignment.department:
            raise ValidationError("Department is required for department assignments.")
        assignment.employee = None
    elif assignment.assignment_type == ScheduleAssignment.AssignmentType.GROUP:
        assignment.employee = None
        assignment.department = None
