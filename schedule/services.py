from django.db import transaction

from schedule.models import (
    BREAK_OUTSIDE_WORK_ERROR,
    TIMETABLE_TIMES_ORDER_ERROR,
    EmployeeScheduleAssignment,
    Schedule,
    Timetable,
    TimetableBreak,
    validate_break_within_timetable,
    validate_timetable_times,
)

__all__ = (
    "BREAK_OUTSIDE_WORK_ERROR",
    "TIMETABLE_TIMES_ORDER_ERROR",
    "validate_break_within_timetable",
    "validate_timetable_times",
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
    )
    if day_change_time is not None:
        timetable.day_change_time = day_change_time
    timetable.full_clean()
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
    if day_change_time is not None:
        timetable.day_change_time = day_change_time
    timetable.work_minutes = work_minutes
    timetable.grace_period_check_out = grace_period_check_out
    timetable.grace_period_minutes = grace_period_minutes
    timetable.count_break_time_as_work_time = count_break_time_as_work_time
    timetable.multiple_in_out = multiple_in_out
    timetable.is_active = is_active
    timetable.full_clean()
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
    # Ordering and flexible-minutes rules live in
    # TimetableBreak.clean(); this only enforces work-window
    # containment against an explicitly supplied window (the formset
    # passes fresh parent values itself).
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
