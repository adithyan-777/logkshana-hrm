"""Daily attendance calculation for the 2-model attendance flow.

Punches stream into ``AttendanceActivity``; this module folds one
(employee, day) window of activities plus the resolved
``EmployeeScheduleAssignment`` into the ``Attendance`` summary row.
Pure pairing/variance math lives in ``attendance.calculation``.
"""

from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from attendance.calculation import (
    day_variances,
    dedupe_punches,
    minutes_between,
    pair_punches,
    scheduled_minutes,
    summarize_pairs,
)
from attendance.models import Attendance, AttendanceActivity
from employees.models import Employee
from schedule.calculation import expected_datetimes
from schedule.models import EmployeeScheduleAssignment
from schedule.selectors import resolve_schedule_for_employee_on_date

DEFAULT_DAY_CHANGE_TIME = time(8, 0)


def _day_window(*, day: date, day_change: time):
    start = timezone.make_aware(
        datetime.combine(day, day_change),
    )
    return start, start + timedelta(days=1)


def _day_punches(*, employee, day: date, day_change: time):
    start, end = _day_window(day=day, day_change=day_change)
    return list(
        AttendanceActivity.objects.filter(
            employee=employee,
            punch_time__gte=start,
            punch_time__lt=end,
        ).order_by("punch_time", "id")
    )


@transaction.atomic
def recalculate_attendance(
    *, employee, day: date, force: bool = False
) -> Attendance | None:
    """(Re)calculate the ``Attendance`` row for one employee and day.

    Returns the row, or None when there is nothing to record (no
    schedule coverage, no punches, and no assignment history).
    Rows with ``is_calculated=False`` are treated as hand-made and left
    alone unless ``force`` is set.
    """
    resolved = resolve_schedule_for_employee_on_date(employee=employee, day=day)
    timetable = resolved.timetable

    existing = Attendance.objects.filter(employee=employee, day=day).first()
    if existing is not None and not existing.is_calculated and not force:
        return existing

    day_change = (
        timetable.day_change_time
        if timetable is not None
        else DEFAULT_DAY_CHANGE_TIME
    )
    punches = _day_punches(employee=employee, day=day, day_change=day_change)

    if not punches:
        return _record_empty_day(
            employee=employee,
            day=day,
            timetable=timetable,
            is_day_off=resolved.is_day_off,
            existing=existing,
        )

    window = (
        timetable.duplicate_punch_window_minutes
        if timetable is not None
        else 1
    )
    break_windows = (
        [(b.start_time, b.end_time) for b in timetable.breaks.all()]
        if timetable is not None
        else []
    )
    pairs = pair_punches(
        dedupe_punches(punches, window_minutes=window),
        allow_multiple_in_out=(
            timetable.multiple_in_out if timetable is not None else False
        ),
        break_windows=break_windows,
    )
    summary = summarize_pairs(pairs)

    if timetable is not None:
        expected_in, expected_out = expected_datetimes(
            timetable=timetable, day=day
        )
        scheduled = scheduled_minutes(
            timetable=timetable,
            expected_in=expected_in,
            expected_out=expected_out,
        )
        late_grace = timetable.grace_period_minutes
        early_grace = (
            timetable.grace_period_minutes
            if timetable.grace_period_check_out
            else 0
        )
    else:
        expected_in = expected_out = None
        scheduled = 0
        late_grace = early_grace = 0

    variances = day_variances(
        first_in=summary.first_in,
        last_out=summary.last_out,
        worked_minutes=summary.worked_minutes,
        expected_in=expected_in,
        expected_out=expected_out,
        scheduled=scheduled,
        late_grace_minutes=late_grace,
        early_grace_minutes=early_grace,
    )

    if resolved.is_day_off:
        # Worked day-off: present, everything counts as overtime.
        status = Attendance.Status.PRESENT
        overtime_minutes = summary.worked_minutes
    elif not summary.has_check_in or not summary.has_check_out:
        status = Attendance.Status.INCOMPLETE
        overtime_minutes = variances.overtime_minutes
    elif variances.late_minutes > 0:
        status = Attendance.Status.LATE
        overtime_minutes = variances.overtime_minutes
    elif variances.early_minutes > 0:
        status = Attendance.Status.EARLY_OUT
        overtime_minutes = variances.overtime_minutes
    else:
        status = Attendance.Status.PRESENT
        overtime_minutes = variances.overtime_minutes

    row, _ = Attendance.objects.update_or_create(
        employee=employee,
        day=day,
        defaults={
            "shift": timetable,
            "total_work_time": timedelta(minutes=summary.worked_minutes),
            "over_time": timedelta(minutes=overtime_minutes),
            "late_time": timedelta(minutes=variances.late_minutes),
            "early_leave_time": timedelta(minutes=variances.early_minutes),
            "status": status,
            "is_calculated": True,
            "calculated_at": timezone.now(),
        },
    )
    row.attendance_activities.set(punches)
    AttendanceActivity.objects.filter(
        pk__in=[punch.pk for punch in punches]
    ).update(is_attendance_processed=True)
    return row


def _record_empty_day(
    *, employee, day: date, timetable, is_day_off: bool, existing
) -> Attendance | None:
    """Record a punch-less day: day-off, absent, or nothing at all."""
    if is_day_off:
        status = Attendance.Status.DAY_OFF
    elif timetable is not None:
        status = Attendance.Status.ABSENT
    elif EmployeeScheduleAssignment.objects.filter(
        employees=employee
    ).exists():
        # Assignment history but no coverage today: absent.
        status = Attendance.Status.ABSENT
    else:
        return None

    row, _ = Attendance.objects.update_or_create(
        employee=employee,
        day=day,
        defaults={
            "shift": timetable,
            "total_work_time": None,
            "over_time": None,
            "status": status,
            "is_calculated": True,
            "calculated_at": timezone.now(),
        },
    )
    row.attendance_activities.clear()
    return row


def calculate_attendance(*, day: date | None = None) -> dict:
    """Print scheduled employees grouped as absentees, late arrivals,
    and work hours.

    Absentees: covered by an active schedule assignment but with no
    activity punch on `day`. An ``Attendance`` row with status
    ``ABSENT`` (or ``DAY_OFF``) is created for each of them via
    ``recalculate_attendance``.
    Late arrivals: punched, but the first punch is after the expected
    check-in (plus timetable grace).
    Work hours: punched-out employees with a complete in/out pair.
    Created attendance: Attendance rows written via recalculate_attendance
    for all scheduled employees with punches on `day` (complete pairs
    become PRESENT/LATE/EARLY_OUT, single/unpaired punches become
    INCOMPLETE) plus ABSENT/DAY_OFF rows for absentees.
    Returns {"absentees": [...], "late_arrivals": [...], "work_hours": ...,
    "created": [...], "incomplete": [...]}
    where work_hours holds (employee, minutes, first_in, last_out) tuples.
    """
    if day is None:
        day = timezone.localtime(timezone.now()).date()

    scheduled_ids = set(
        EmployeeScheduleAssignment.objects.filter(
            is_active=True,
            start_date__lte=day,
            schedule__is_active=True,
        )
        .filter(Q(end_date__gte=day) | Q(end_date__isnull=True))
        .values_list("employees__pk", flat=True)
    )
    scheduled_ids.discard(None)

    punched_ids = set(
        AttendanceActivity.objects.filter(punch_time__date=day).values_list(
            "employee_id", flat=True
        )
    )

    absentees = list(
        Employee.objects.filter(pk__in=scheduled_ids - punched_ids).order_by(
            "first_name", "last_name"
        )
    )

    late_arrivals = []
    work_hours = []
    incomplete = []
    eligible_for_creation = []
    for employee in (
        Employee.objects.filter(pk__in=scheduled_ids & punched_ids)
        .order_by("first_name", "last_name")
        .iterator()
    ):
        punches = list(
            AttendanceActivity.objects.filter(
                employee=employee, punch_time__date=day
            ).order_by("punch_time")
        )
        if not punches:
            continue
        # Every punched scheduled employee gets an Attendance row:
        # complete pairs -> PRESENT/LATE/EARLY_OUT, single or unpaired
        # punches -> INCOMPLETE (handled inside recalculate_attendance).
        eligible_for_creation.append(employee)
        resolved = resolve_schedule_for_employee_on_date(
            employee=employee, day=day
        )
        timetable = resolved.timetable
        if (
            not resolved.is_day_off
            and timetable is not None
        ):
            expected_in, _ = expected_datetimes(
                timetable=timetable, day=day
            )
            if expected_in is not None:
                late_minutes = minutes_between(
                    expected_in, punches[0].punch_time
                ) - (timetable.grace_period_minutes or 0)
                if late_minutes > 0:
                    late_arrivals.append((employee, late_minutes))
        summary = summarize_pairs(
            pair_punches(
                dedupe_punches(
                    punches,
                    window_minutes=(
                        timetable.duplicate_punch_window_minutes
                        if timetable is not None
                        else 1
                    ),
                ),
                allow_multiple_in_out=(
                    timetable.multiple_in_out
                    if timetable is not None
                    else False
                ),
                break_windows=(
                    [(b.start_time, b.end_time) for b in timetable.breaks.all()]
                    if timetable is not None
                    else []
                ),
            )
        )
        if summary.has_check_in and summary.has_check_out:
            work_hours.append(
                (
                    employee,
                    summary.worked_minutes,
                    summary.first_in,
                    summary.last_out,
                )
            )
        else:
            incomplete.append(employee)

    for employee in absentees:
        print(employee.full_name)
    print("--------------------------------------------------")
    print("Late arrivals:")
    print("--------------------------------------------------")
    for employee, late_minutes in late_arrivals:
        print(f"{employee.full_name} (+{late_minutes}m)")
    print("--------------------------------------------------")
    print("Work hours:")
    print("--------------------------------------------------")
    for employee, worked_minutes, first_in, last_out in work_hours:
        hours, minutes = divmod(worked_minutes, 60)
        print("--------------------------------------------------")
        print(
            f"{employee.full_name}: {hours}h {minutes:02d}m "
            f"(in {first_in:%H:%M} out {last_out:%H:%M})"
        )
        print("--------------------------------------------------")
    print("--------------------------------------------------")
    print("Created attendance:")
    print("--------------------------------------------------")
    created = []
    for employee in eligible_for_creation:
        # recalculate_attendance is atomic per employee and never
        # overwrites hand-made rows (is_calculated=False) without force.
        # Complete pairs -> PRESENT/LATE/EARLY_OUT; single/unpaired
        # punches -> INCOMPLETE.
        row = recalculate_attendance(employee=employee, day=day)
        if row is not None:
            created.append(row)
            print(f"{employee.full_name} -> {row.status}")
    # Absentees (scheduled but never punched) get ABSENT rows
    # (or DAY_OFF when the day is a day-off). recalculate_attendance
    # routes punch-less days to _record_empty_day which already uses
    # Attendance.Status.ABSENT / DAY_OFF — both exist in
    # Attendance.Status, so no new status needs to be created.
    for employee in absentees:
        row = recalculate_attendance(employee=employee, day=day)
        if row is not None:
            created.append(row)
            print(f"{employee.full_name} -> {row.status}")
    print("--------------------------------------------------")
    return {
        "absentees": absentees,
        "late_arrivals": late_arrivals,
        "work_hours": work_hours,
        "created": created,
        "incomplete": incomplete,
    }


# from django_tenants.utils import schema_context
# with schema_context('tty'):
#     from attendance.recalculation import calculate_attendance
#     calculate_attendance()
