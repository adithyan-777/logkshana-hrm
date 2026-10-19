"""Daily attendance calculation, driven by materialized shift rows.

``ScheduledShiftDay`` is the single definition of the plan: one row per
(employee, day) with absolute shift times, a frozen timetable snapshot,
and an attribution window. Punches link to their row via
``AttendanceActivity.scheduled_shift`` (window containment); this module
folds one row plus its punches into the ``Attendance`` summary row.

Layers:

* attribution   — ``link_punch_to_shift`` / ``shift_punches``: which
  punches belong to a row (window containment, nothing else).
* calculation   — ``build_shift_result``: pure first-in/last-out math
  against the row's own times. Writes nothing.
* persistence   — ``recalculate_shift`` / ``recalculate_attendance``:
  the only writers.
* reporting     — ``day_report``: read-only over persisted rows.
* orchestration — ``ensure_day`` / ``calculate_attendance``.

No live schedule resolution happens here: assignments, overrides,
repeat rules and holidays are all resolved once, at materialization
time (``schedule.services.get_or_materialize_shift``).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from attendance.calculation import minutes_between
from attendance.models import Attendance, AttendanceActivity
from employees.models import Employee
from schedule.models import (
    EmployeeScheduleAssignment,
    EmployeeScheduleOverride,
    ScheduledShiftDay,
)
from schedule.services import find_shift_for_punch, get_or_materialize_shift

# --------------------------------------------------------------------------
# Attribution — window containment is the single definition of belonging.
# --------------------------------------------------------------------------


def link_punch_to_shift(*, punch: AttendanceActivity):
    """Point one punch at the shift row whose window contains it."""
    shift = find_shift_for_punch(
        employee=punch.employee, timestamp=punch.punch_time
    )
    if shift is not None and punch.scheduled_shift_id != shift.pk:
        punch.scheduled_shift = shift
        punch.save(update_fields=["scheduled_shift"])
    return shift


def shift_punches(*, shift: ScheduledShiftDay) -> list:
    """All punches belonging to ``shift``, in time order.

    Strays inside the row's window are linked on the way in, so a punch
    created before its row existed still lands correctly. Rows without a
    window (day-off / holiday) collect the calendar day's punches.
    """
    if shift.window_start is not None and shift.window_end is not None:
        strays = AttendanceActivity.objects.filter(
            employee=shift.employee,
            punch_time__gte=shift.window_start,
            punch_time__lt=shift.window_end,
            scheduled_shift__isnull=True,
        )
        if strays.exists():
            strays.update(scheduled_shift=shift)
    else:
        day_start = timezone.make_aware(datetime.combine(shift.day, time.min))
        strays = AttendanceActivity.objects.filter(
            employee=shift.employee,
            punch_time__gte=day_start,
            punch_time__lt=day_start + timedelta(days=1),
            scheduled_shift__isnull=True,
        )
        if strays.exists():
            strays.update(scheduled_shift=shift)
    return list(
        shift.attendance_activities.order_by("punch_time", "id")
    )


# --------------------------------------------------------------------------
# Calculation — pure: one shift row + its punches -> what the row says.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DayResult:
    """Everything needed to write one (employee, day) row. Writes nothing."""

    day: date
    employee: Employee
    status: str
    row_values: dict
    punches: tuple = ()


def _snapshot_value(*, shift: ScheduledShiftDay, key: str, default=None):
    """Read a frozen param, falling back to the live timetable.

    Rows materialized before snapshots existed (or with a deleted
    timetable) still calculate from whatever is available.
    """
    snapshot = shift.timetable_snapshot or {}
    if key in snapshot:
        return snapshot[key]
    timetable = shift.timetable
    return getattr(timetable, key, default) if timetable is not None else default


def _snapshot_breaks(*, shift: ScheduledShiftDay) -> list:
    """Break windows as ``(start, end, type, minutes)`` time tuples."""
    snapshot = shift.timetable_snapshot or {}
    raw = snapshot.get("breaks")
    if raw is None:
        if shift.timetable is None:
            return []
        return [
            (b.start_time, b.end_time, b.break_time_type, b.break_time_minutes)
            for b in shift.timetable.breaks.all()
        ]
    out = []
    for item in raw:
        out.append(
            (
                time.fromisoformat(item["start_time"]),
                time.fromisoformat(item["end_time"]),
                item.get("break_time_type", "fixed"),
                item.get("break_time_minutes"),
            )
        )
    return out


def _break_overlap_minutes(*, start: datetime, end: datetime, breaks: list) -> int:
    """Unpaid break minutes overlapping ``[start, end)``.

    Each break counts once: its wall-clock window is scored on every
    calendar day the shift touches and the best overlap wins (covers
    overnight shifts with early-morning breaks).
    """
    unpaid = 0
    span_days = (end.date() - start.date()).days
    for break_start, break_end, break_type, break_minutes in breaks:
        best = 0
        for offset in range(-1, span_days + 2):
            day = (start + timedelta(days=offset)).date()
            window_start = timezone.make_aware(
                datetime.combine(day, break_start)
            )
            window_end = timezone.make_aware(datetime.combine(day, break_end))
            if window_end <= window_start:
                continue
            best = max(
                best,
                minutes_between(max(start, window_start), min(end, window_end)),
            )
        if break_type == "flexible":
            best = min(best, break_minutes or 0)
        unpaid += best
    return unpaid


def build_shift_result(*, shift: ScheduledShiftDay) -> DayResult:
    """Compute the ``Attendance`` values for one shift row. Writes nothing."""
    punches = shift_punches(shift=shift)

    if not punches:
        status = {
            ScheduledShiftDay.DayType.DAY_OFF: Attendance.Status.DAY_OFF,
            ScheduledShiftDay.DayType.HOLIDAY: Attendance.Status.HOLIDAY,
        }.get(shift.day_type, Attendance.Status.ABSENT)
        return DayResult(
            day=shift.day,
            employee=shift.employee,
            status=status,
            punches=(),
            row_values=_row_values(
                shift=shift,
                check_in=None,
                check_out=None,
                status=status,
                worked_minutes=0,
                overtime_minutes=0,
                late_minutes=0,
                early_minutes=0,
            ),
        )

    first_in = punches[0].punch_time
    last_out = punches[-1].punch_time

    if shift.day_type != ScheduledShiftDay.DayType.WORKING or (
        shift.shift_start is None or shift.shift_end is None
    ):
        # Worked day-off / holiday / unscheduled: present, everything
        # counts as overtime.
        worked_minutes = (
            minutes_between(first_in, last_out) if len(punches) > 1 else 0
        )
        status = Attendance.Status.PRESENT
        if len(punches) == 1:
            status = Attendance.Status.INCOMPLETE
            worked_minutes = 0
        return DayResult(
            day=shift.day,
            employee=shift.employee,
            status=status,
            punches=tuple(punches),
            row_values=_row_values(
                shift=shift,
                check_in=first_in,
                check_out=last_out if len(punches) > 1 else None,
                status=status,
                worked_minutes=worked_minutes,
                overtime_minutes=worked_minutes,
                late_minutes=0,
                early_minutes=0,
            ),
        )

    if len(punches) == 1:
        # Lone check-in: incomplete, but lateness is still recorded (a
        # late employee who never checked out is INCOMPLETE *and* late).
        grace = _snapshot_value(
            shift=shift, key="grace_period_minutes", default=0
        ) or 0
        late_minutes = max(
            0, minutes_between(shift.shift_start, first_in) - max(0, grace)
        )
        return DayResult(
            day=shift.day,
            employee=shift.employee,
            status=Attendance.Status.INCOMPLETE,
            punches=tuple(punches),
            row_values=_row_values(
                shift=shift,
                check_in=first_in,
                check_out=None,
                status=Attendance.Status.INCOMPLETE,
                worked_minutes=0,
                overtime_minutes=0,
                late_minutes=late_minutes,
                early_minutes=0,
            ),
        )

    worked_minutes = minutes_between(first_in, last_out)
    scheduled_minutes = max(
        0,
        minutes_between(shift.shift_start, shift.shift_end)
        - _break_overlap_minutes(
            start=shift.shift_start,
            end=shift.shift_end,
            breaks=_snapshot_breaks(shift=shift),
        ),
    )
    grace = _snapshot_value(
        shift=shift, key="grace_period_minutes", default=0
    ) or 0
    checkout_grace = (
        grace
        if _snapshot_value(
            shift=shift, key="grace_period_check_out", default=False
        )
        else 0
    )
    late_minutes = max(
        0, minutes_between(shift.shift_start, first_in) - max(0, grace)
    )
    early_minutes = max(
        0, minutes_between(last_out, shift.shift_end) - max(0, checkout_grace)
    )
    overtime_minutes = max(0, worked_minutes - scheduled_minutes)

    if late_minutes > 0:
        status = Attendance.Status.LATE
    elif early_minutes > 0:
        status = Attendance.Status.EARLY_OUT
    else:
        status = Attendance.Status.PRESENT

    return DayResult(
        day=shift.day,
        employee=shift.employee,
        status=status,
        punches=tuple(punches),
        row_values=_row_values(
            shift=shift,
            check_in=first_in,
            check_out=last_out,
            status=status,
            worked_minutes=worked_minutes,
            overtime_minutes=overtime_minutes,
            late_minutes=late_minutes,
            early_minutes=early_minutes,
        ),
    )


def _row_values(
    *,
    shift: ScheduledShiftDay,
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
    The snapshot is the row's frozen copy (built on demand for legacy
    rows), so later timetable edits never rewrite history.
    """
    from schedule.services import build_timetable_snapshot

    return {
        "shift": shift.timetable,
        "shift_snapshot": (
            shift.timetable_snapshot
            or build_timetable_snapshot(timetable=shift.timetable)
        ),
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


# --------------------------------------------------------------------------
# Persistence — the only writer.
# --------------------------------------------------------------------------


def _unscheduled_shift_if_punched(*, employee, day: date):
    """A plan row for punches with no coverage, else None."""
    day_start = timezone.make_aware(datetime.combine(day, time.min))
    has_punches = AttendanceActivity.objects.filter(
        employee=employee,
        punch_time__gte=day_start,
        punch_time__lt=day_start + timedelta(days=1),
    ).exists()
    if not has_punches:
        return None
    return ScheduledShiftDay.objects.create(
        employee=employee,
        day=day,
        day_type=ScheduledShiftDay.DayType.WORKING,
        source=ScheduledShiftDay.Source.UNSCHEDULED,
    )


@transaction.atomic
def recalculate_shift(*, shift: ScheduledShiftDay, force: bool = False):
    """(Re)calculate the ``Attendance`` row for one shift row."""
    existing = Attendance.objects.filter(
        employee=shift.employee, day=shift.day
    ).first()
    if existing is not None and not existing.is_calculated and not force:
        return existing
    return _persist(result=build_shift_result(shift=shift))


@transaction.atomic
def recalculate_attendance(
    *, employee, day: date, force: bool = False
) -> Attendance | None:
    """(Re)calculate the ``Attendance`` row for one employee and day.

    Returns the row, or None when there is genuinely nothing to record
    (no plan coverage and no punches). Rows with ``is_calculated=False``
    are treated as hand-made and left alone unless ``force`` is set.
    """
    existing = Attendance.objects.filter(employee=employee, day=day).first()
    if existing is not None and not existing.is_calculated and not force:
        return existing

    shift, _ = get_or_materialize_shift(employee=employee, day=day)
    if shift is None:
        shift = _unscheduled_shift_if_punched(employee=employee, day=day)
    if shift is None:
        return None
    return recalculate_shift(shift=shift, force=force)


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

    Consumed punches point at both the row and its shift plan row.
    Punches the row drops keep their shift link: the shift is still
    their plan home even when this row ignores them.
    """
    shift = (
        ScheduledShiftDay.objects.filter(employee=row.employee, day=row.day).first()
    )
    punch_ids = [punch.pk for punch in punches]
    AttendanceActivity.objects.filter(attendance=row).exclude(
        pk__in=punch_ids
    ).update(attendance=None)
    if punch_ids:
        AttendanceActivity.objects.filter(pk__in=punch_ids).update(
            attendance=row, scheduled_shift=shift
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
    """Punches near ``day`` that no row consumed and no shift claimed.

    A calendar-day superset (plus one) covers every attribution window
    without re-deriving day geometry.
    """
    window_start = timezone.make_aware(datetime.combine(day, time.min))
    return tuple(
        AttendanceActivity.objects.filter(
            attendance__isnull=True,
            punch_time__gte=window_start,
            punch_time__lt=window_start + timedelta(days=2),
        ).order_by("employee_id", "punch_time", "id")
    )


# --------------------------------------------------------------------------
# Orchestration.
# --------------------------------------------------------------------------


def ensure_day(*, day: date) -> list:
    """Write an ``Attendance`` row for every shift row of ``day``.

    Missing plan rows are materialized first for the cheap candidate
    superset (assignments, overrides, punch owners); rows that genuinely
    have nothing to record resolve to None.
    """
    for shift in ScheduledShiftDay.objects.filter(day=day):
        recalculate_shift(shift=shift)

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
        if row is not None and row not in created:
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

    return {
        "absentees": absentees,
        "late_arrivals": late_arrivals,
        "work_hours": work_hours,
        "created": created,
        "incomplete": incomplete,
    }

