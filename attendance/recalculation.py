"""Daily attendance calculation for the 2-model attendance flow.

Punches stream into ``AttendanceActivity``; this module folds one
(employee, day) window of activities plus the resolved
``EmployeeScheduleAssignment`` into the ``Attendance`` summary row.
Pure pairing/variance math lives in ``attendance.calculation``.
"""

from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from attendance.calculation import (
    day_variances,
    dedupe_punches,
    pair_punches,
    scheduled_minutes,
    summarize_pairs,
)
from attendance.models import Attendance, AttendanceActivity
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
    pairs = pair_punches(
        dedupe_punches(punches, window_minutes=window),
        allow_multiple_in_out=(
            timetable.multiple_in_out if timetable is not None else False
        ),
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
