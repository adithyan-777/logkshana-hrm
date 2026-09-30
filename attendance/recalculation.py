"""Daily attendance calculation for the 2-model attendance flow.

Punches stream into ``AttendanceActivity``; this module folds one
(employee, day) window of activities plus the resolved schedule into
the ``Attendance`` summary row.

Each rule has exactly one definition, in its own layer:

* day geometry  — ``day_window`` / ``punches_for``: what "this day"
  means (the shift's ``day_change_time``, not midnight).
* calculation   — ``build_day_result``: pure, writes nothing.
* persistence   — ``recalculate_attendance``: the only writer.
* reporting     — ``day_report``: read-only over persisted rows, so it
  can never disagree with the rows it describes.
* orchestration — ``ensure_day`` / ``calculate_attendance``.

Pure pairing/variance math lives in ``attendance.calculation``.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from attendance.calculation import (
    DaySummary,
    DayVariances,
    attendance_day_for_punch,
    day_variances,
    dedupe_punches,
    pair_punches,
    scheduled_minutes,
    summarize_pairs,
)
from attendance.models import Attendance, AttendanceActivity
from employees.models import Employee
from schedule.calculation import expected_datetimes
from schedule.models import EmployeeScheduleAssignment, EmployeeScheduleOverride
from schedule.selectors import resolve_schedule_for_employee_on_date

DEFAULT_DAY_CHANGE_TIME = time(8, 0)


# --------------------------------------------------------------------------
# Day geometry — the single definition of "the day".
# --------------------------------------------------------------------------


def day_window(*, day: date, day_change: time) -> tuple[datetime, datetime]:
    """The ``[start, end)`` window of punches attributed to ``day``."""
    start = timezone.make_aware(datetime.combine(day, day_change))
    return start, start + timedelta(days=1)


def punches_for(*, employee, day: date, day_change: time) -> list:
    """All of ``employee``'s punches attributed to ``day``, in time order."""
    start, end = day_window(day=day, day_change=day_change)
    return list(
        AttendanceActivity.objects.filter(
            employee=employee,
            punch_time__gte=start,
            punch_time__lt=end,
        ).order_by("punch_time", "id")
    )


def _day_change_for(timetable) -> time:
    return timetable.day_change_time if timetable is not None else DEFAULT_DAY_CHANGE_TIME


# --------------------------------------------------------------------------
# Calculation — pure: punches + resolved schedule -> what the row should say.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DayResult:
    """Everything needed to write one (employee, day) row. Writes nothing."""

    day: date
    employee: Employee
    status: str
    row_values: dict
    punches: tuple = ()
    summary: DaySummary | None = None
    variances: DayVariances | None = None


def build_day_result(*, employee, day: date) -> DayResult | None:
    """Compute the ``Attendance`` values for one employee and day.

    Returns None when there is genuinely nothing to record (no schedule
    coverage, no punches, no assignment history). Writes nothing: the
    caller decides whether to persist.
    """
    resolved = resolve_schedule_for_employee_on_date(employee=employee, day=day)
    timetable = resolved.timetable
    punches = punches_for(
        employee=employee,
        day=day,
        day_change=_day_change_for(timetable),
    )

    if not punches:
        status = _empty_day_status(
            employee=employee,
            timetable=timetable,
            is_day_off=resolved.is_day_off,
        )
        if status is None:
            return None
        return DayResult(
            day=day,
            employee=employee,
            status=status,
            punches=(),
            summary=None,
            variances=None,
            row_values=_row_values(
                shift=timetable,
                check_in=None,
                check_out=None,
                status=status,
                worked_minutes=0,
                overtime_minutes=0,
                late_minutes=0,
                early_minutes=0,
            ),
        )

    window = (
        timetable.duplicate_punch_window_minutes if timetable is not None else 1
    )
    break_windows = (
        [(b.start_time, b.end_time) for b in timetable.breaks.all()]
        if timetable is not None
        else []
    )
    summary = summarize_pairs(
        pair_punches(
            dedupe_punches(punches, window_minutes=window),
            allow_multiple_in_out=(
                timetable.multiple_in_out if timetable is not None else False
            ),
            break_windows=break_windows,
        )
    )

    if timetable is not None:
        expected_in, expected_out = expected_datetimes(timetable=timetable, day=day)
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

    return DayResult(
        day=day,
        employee=employee,
        status=status,
        punches=tuple(punches),
        summary=summary,
        variances=variances,
        row_values=_row_values(
            shift=timetable,
            check_in=summary.first_in,
            check_out=summary.last_out,
            status=status,
            worked_minutes=summary.worked_minutes,
            overtime_minutes=overtime_minutes,
            late_minutes=variances.late_minutes,
            early_minutes=variances.early_minutes,
        ),
    )


def _empty_day_status(*, employee, timetable, is_day_off: bool) -> str | None:
    """Status for a punch-less day, or None when nothing should be recorded."""
    if is_day_off:
        return Attendance.Status.DAY_OFF
    if timetable is not None:
        return Attendance.Status.ABSENT
    if EmployeeScheduleAssignment.objects.filter(employees=employee).exists():
        # Assignment history but no coverage today: absent.
        return Attendance.Status.ABSENT
    return None


def _row_values(
    *,
    shift,
    check_in,
    check_out,
    status: str,
    worked_minutes: int,
    overtime_minutes: int,
    late_minutes: int,
    early_minutes: int,
) -> dict:
    """The exact ``defaults`` dict for a row.

    Every duration is always written: an empty day zeroes them, so a
    previous LATE can't leave a stale ``late_time`` on an ABSENT row.
    """
    return {
        "shift": shift,
        "shift_snapshot": _shift_snapshot(shift),
        "check_in": check_in,
        "check_out": check_out,
        "total_work_time": timedelta(minutes=worked_minutes),
        "over_time": timedelta(minutes=overtime_minutes),
        "late_time": timedelta(minutes=late_minutes),
        "early_leave_time": timedelta(minutes=early_minutes),
        "status": status,
        "is_calculated": True,
        "calculated_at": timezone.now(),
    }


def _shift_snapshot(timetable) -> dict | None:
    """Freeze the shift params that produced a row's numbers."""
    if timetable is None:
        return None
    return {
        "name": timetable.name,
        "check_in": timetable.check_in.isoformat() if timetable.check_in else None,
        "check_out": timetable.check_out.isoformat() if timetable.check_out else None,
        "day_change_time": timetable.day_change_time.isoformat(),
        "grace_period_minutes": timetable.grace_period_minutes,
        "duplicate_punch_window_minutes": timetable.duplicate_punch_window_minutes,
        "multiple_in_out": timetable.multiple_in_out,
    }


# --------------------------------------------------------------------------
# Persistence — the only writer.
# --------------------------------------------------------------------------


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
    existing = Attendance.objects.filter(employee=employee, day=day).first()
    if existing is not None and not existing.is_calculated and not force:
        return existing

    result = build_day_result(employee=employee, day=day)
    if result is None:
        return None
    return _persist(result=result)


def _persist(*, result: DayResult) -> Attendance:
    row, _ = Attendance.objects.update_or_create(
        employee=result.employee,
        day=result.day,
        defaults=result.row_values,
    )
    _set_row_punches(row=row, punches=result.punches)
    return row


def _set_row_punches(*, row: Attendance, punches) -> None:
    """Make ``row``'s linked punches exactly ``punches``.

    Uses ``all_objects`` so soft-deleted punches are unlinked too —
    the default manager hides them, which would leave a stale
    ``attendance_id`` behind on a deleted row.
    """
    punch_ids = [punch.pk for punch in punches]
    AttendanceActivity.all_objects.filter(attendance=row).exclude(
        pk__in=punch_ids
    ).update(attendance=None)
    if punch_ids:
        AttendanceActivity.all_objects.filter(pk__in=punch_ids).update(
            attendance=row
        )


# --------------------------------------------------------------------------
# Reporting — read-only over persisted rows.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DayReport:
    """One day's ``Attendance`` rows, grouped by status.

    Buckets are predicates over columns the writer already persisted;
    nothing is re-derived from punches, so the report cannot disagree
    with the rows it describes. ``late_arrivals`` is ``late_time > 0``
    (not ``status == LATE``): a late employee who never checked out is
    INCOMPLETE *and* late. ``work_hours`` is a complete pair.
    """

    day: date
    rows: tuple
    present: tuple
    late: tuple
    early_out: tuple
    incomplete: tuple
    absent: tuple
    day_off: tuple
    leave: tuple
    holiday: tuple
    late_arrivals: tuple
    work_hours: tuple
    unlinked_punches: tuple


def day_report(*, day: date) -> DayReport:
    """Group the persisted rows for ``day``. Reads only, never writes."""
    rows = tuple(
        Attendance.objects.filter(day=day)
        .select_related("employee", "shift")
        .order_by("employee__first_name", "employee__last_name", "employee__pk")
    )

    def bucket(status: str) -> tuple:
        return tuple(row for row in rows if row.status == status)

    return DayReport(
        day=day,
        rows=rows,
        present=bucket(Attendance.Status.PRESENT),
        late=bucket(Attendance.Status.LATE),
        early_out=bucket(Attendance.Status.EARLY_OUT),
        incomplete=bucket(Attendance.Status.INCOMPLETE),
        absent=bucket(Attendance.Status.ABSENT),
        day_off=bucket(Attendance.Status.DAY_OFF),
        leave=bucket(Attendance.Status.LEAVE),
        holiday=bucket(Attendance.Status.HOLIDAY),
        late_arrivals=tuple(row for row in rows if row.late_time > timedelta(0)),
        work_hours=tuple(
            row for row in rows if row.check_in is not None and row.check_out is not None
        ),
        unlinked_punches=_unlinked_punches(day=day),
    )


def _unlinked_punches(*, day: date) -> tuple:
    """Punches attributed to ``day`` that no row consumed.

    Diagnostics for the gap ``ensure_day`` can't see: employees whose
    punches exist but who have no schedule coverage (or were excluded
    from the fanout). Attribution reuses the shared day-geometry rule
    instead of the calendar date, so post-midnight check-outs are not
    blamed on the wrong day.
    """
    # A punch attributed to `day` lands in [day+change, day+1+change),
    # so calendar dates {day, day+1} are a safe superset for any change.
    window_start = timezone.make_aware(datetime.combine(day, time.min))
    candidates = list(
        AttendanceActivity.objects.filter(
            attendance__isnull=True,
            punch_time__gte=window_start,
            punch_time__lt=window_start + timedelta(days=2),
        ).order_by("employee_id", "punch_time", "id")
    )
    if not candidates:
        return ()

    employees = Employee.objects.in_bulk({p.employee_id for p in candidates})
    kept: list = []
    index = 0
    while index < len(candidates):
        employee_id = candidates[index].employee_id
        group: list = []
        while (
            index < len(candidates)
            and candidates[index].employee_id == employee_id
        ):
            group.append(candidates[index])
            index += 1
        employee = employees.get(employee_id)
        if employee is None:
            continue
        day_change = _day_change_for(
            resolve_schedule_for_employee_on_date(
                employee=employee, day=day
            ).timetable
        )
        kept.extend(
            punch
            for punch in group
            if attendance_day_for_punch(
                timestamp=punch.punch_time, day_change_time=day_change
            )
            == day
        )
    return tuple(kept)


# --------------------------------------------------------------------------
# Orchestration.
# --------------------------------------------------------------------------


def ensure_day(*, day: date) -> list:
    """Write an ``Attendance`` row for everyone who should have one.

    The candidate set is a cheap superset — active assignments covering
    ``day``, one-day overrides, and anyone who punched on ``day`` or the
    following day — and each candidate is then resolved individually by
    ``recalculate_attendance``, which returns None when there is
    genuinely nothing to record. Repeat rules, assignment priority,
    day-off overrides and active-timetable checks therefore all come
    from the one resolver instead of a raw assignment query, and
    punched-but-unscheduled employees are not silently dropped.
    """
    candidates: set = set(
        EmployeeScheduleAssignment.objects.filter(
            is_active=True,
            start_date__lte=day,
            schedule__is_active=True,
        )
        .filter(Q(end_date__gte=day) | Q(end_date__isnull=True))
        .values_list("employees__pk", flat=True)
    )
    candidates |= set(
        EmployeeScheduleOverride.objects.filter(date=day).values_list(
            "employee_id", flat=True
        )
    )
    candidates |= set(
        AttendanceActivity.objects.filter(
            punch_time__date__in=[day, day + timedelta(days=1)]
        ).values_list("employee_id", flat=True)
    )
    candidates.discard(None)

    created = []
    employees = Employee.objects.filter(
        pk__in=candidates, is_active=True
    ).order_by("first_name", "last_name", "pk")
    for employee in employees.iterator():
        row = recalculate_attendance(employee=employee, day=day)
        if row is not None:
            created.append(row)
    return created


def calculate_attendance(*, day: date | None = None) -> dict:
    """Ensure the day's rows, print the grouped report, return it.

    Two phases, so the numbers printed and returned are the rows that
    were written — there is no second calculation that can disagree
    with them. Prefer ``ensure_day`` + ``day_report`` when you don't
    want the console output.
    """
    if day is None:
        day = timezone.localtime(timezone.now()).date()

    created = ensure_day(day=day)
    report = day_report(day=day)

    absentees = [row.employee for row in report.absent]
    late_arrivals = [(row.employee, row.late_minutes) for row in report.late_arrivals]
    work_hours = [
        (row.employee, row.worked_minutes, row.check_in, row.check_out)
        for row in report.work_hours
    ]
    incomplete = [row.employee for row in report.incomplete]

    _print_report(
        absentees=absentees,
        late_arrivals=late_arrivals,
        work_hours=work_hours,
        created=created,
    )

    return {
        "absentees": absentees,
        "late_arrivals": late_arrivals,
        "work_hours": work_hours,
        "created": created,
        "incomplete": incomplete,
    }


def _print_report(*, absentees, late_arrivals, work_hours, created) -> None:
    separator = "-" * 50
    print("Absentees:")
    print(separator)
    for employee in absentees:
        print(employee.full_name)
    print(separator)
    print("Late arrivals:")
    print(separator)
    for employee, late_minutes in late_arrivals:
        print(f"{employee.full_name} (+{late_minutes}m)")
    print(separator)
    print("Work hours:")
    print(separator)
    for employee, worked_minutes, check_in, check_out in work_hours:
        hours, minutes = divmod(worked_minutes, 60)
        print(
            f"{employee.full_name}: {hours}h {minutes:02d}m "
            f"(in {check_in:%H:%M} out {check_out:%H:%M})"
        )
    print(separator)
    print("Created attendance:")
    print(separator)
    for row in created:
        print(f"{row.employee.full_name} -> {row.status}")
    print(separator)
