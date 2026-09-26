from datetime import date, datetime, time, timedelta
from typing import NamedTuple

from django.utils import timezone


def attendance_day_for_punch(*, timestamp, day_change_time: time) -> date:
    """
    The attendance day a punch belongs to.

    Punches earlier than day_change_time (in local time) belong to the
    previous attendance day, so the check-out of an overnight shift
    (e.g. 06:15 the next morning) lands on the day the shift started.
    Naive timestamps are interpreted in the local timezone.
    """
    if timezone.is_naive(timestamp):
        timestamp = timezone.make_aware(timestamp)

    local_punch = timezone.localtime(timestamp)
    if local_punch.time() < day_change_time:
        return local_punch.date() - timedelta(days=1)
    return local_punch.date()


# ZKTeco ATTLOG punch states. Most devices report every punch as 0
# unless function keys are configured, so only the explicit
# check-out states map to OUT — everything else stays UNKNOWN and
# pairing treats the first punch of the day as check-in.
_GATEWAY_OUT_STATUSES = {
    1,  # Check out
    2,  # Break out
    5,  # Overtime out
}


def direction_from_gateway_status(status) -> str:
    """Map a device-gateway punch ``status`` to a punch direction.

    Returns ``"out"`` for explicit check-out states, ``"unknown"``
    otherwise (missing/garbled values included) so pairing falls back
    to alternating IN/OUT.
    """
    try:
        code = int(status)
    except (TypeError, ValueError):
        return "unknown"
    return "out" if code in _GATEWAY_OUT_STATUSES else "unknown"


def dedupe_punches(punches, *, window_minutes: int = 1) -> list:
    """Drop punches within ``window_minutes`` of the previous kept punch.

    ``punches`` must be sorted by punch_time ascending. The first punch
    is always kept (a device double-tap at check-in still counts once).
    """
    kept = []
    window = timedelta(minutes=max(0, window_minutes))
    for punch in punches:
        if kept and punch.punch_time - kept[-1].punch_time <= window:
            continue
        kept.append(punch)
    return kept


def effective_directions(punches, *, break_windows=()) -> list[str]:
    """Resolve one direction per punch for pairing.

    Explicit IN/OUT punches keep their direction; UNKNOWN punches
    alternate (IN when no open check-in, OUT otherwise), except an
    UNKNOWN punch inside a scheduled break window counts as going out
    for break, and the punch after a break counts as back in.

    ``break_windows`` is an iterable of ``(start_time, end_time)``
    wall-clock pairs taken from the timetable's breaks.
    """
    directions = []
    open_in = False
    expect_in_after_break = False
    for punch in punches:
        direction = punch.direction
        if direction not in ("in", "out"):
            punch_time = punch.punch_time
            if timezone.is_naive(punch_time):
                punch_time = timezone.make_aware(punch_time)
            local_time = timezone.localtime(punch_time).time()
            in_break = any(
                start <= local_time < end for start, end in break_windows
            )
            if in_break:
                # Going for break: close the open period (or lone
                # break punch when nothing is open).
                direction = "out"
                expect_in_after_break = True
            elif expect_in_after_break:
                # Coming back: punch again as in.
                direction = "in"
                expect_in_after_break = False
            else:
                direction = "out" if open_in else "in"
        else:
            expect_in_after_break = False
        directions.append(direction)
        open_in = direction == "in"
    return directions


def pair_punches(
    punches,
    *,
    allow_multiple_in_out: bool = False,
    break_windows=(),
) -> list[tuple]:
    """Pair sorted punches into (check_in, check_out) tuples.

    Either side may be None (open period / lone check-out). Pairing is
    positional: consecutive IN -> OUT punches form a period. A second
    IN while one is open closes the previous period as open (invalid)
    when ``allow_multiple_in_out`` is set, otherwise the first
    check-in wins and the repeat is ignored. UNKNOWN punches inside
    ``break_windows`` count as going out for break (see
    ``effective_directions``).
    """
    punches = list(punches)
    pairs = []
    pending_in = None
    for punch, direction in zip(
        punches, effective_directions(punches, break_windows=break_windows)
    ):
        if direction == "in":
            if pending_in is None:
                pending_in = punch
            elif allow_multiple_in_out:
                pairs.append((pending_in, None))
                pending_in = punch
            # else: first check-in wins, ignore the repeat.
        elif pending_in is not None:
            pairs.append((pending_in, punch))
            pending_in = None
        else:
            pairs.append((None, punch))
    if pending_in is not None:
        pairs.append((pending_in, None))
    return pairs


class DaySummary(NamedTuple):
    """Time totals derived from one day's paired punches."""

    pairs: list[tuple]
    first_in: datetime | None
    last_out: datetime | None
    worked_minutes: int
    break_minutes: int

    @property
    def has_check_in(self) -> bool:
        return self.first_in is not None

    @property
    def has_check_out(self) -> bool:
        return self.last_out is not None


def summarize_pairs(pairs) -> DaySummary:
    """Collapse paired punches into first/last times and minute totals.

    ``pairs`` must be in time order. Break time is the span between
    first check-in and last check-out minus worked minutes.
    """
    pairs = list(pairs)
    first_in = next((c.punch_time for c, _ in pairs if c is not None), None)
    last_out = None
    for _, check_out in pairs:
        if check_out is not None:
            last_out = check_out.punch_time
    worked_minutes = sum(
        minutes_between(c.punch_time, o.punch_time)
        for c, o in pairs
        if c is not None and o is not None
    )
    span_minutes = (
        minutes_between(first_in, last_out)
        if first_in is not None and last_out is not None
        else 0
    )
    return DaySummary(
        pairs=pairs,
        first_in=first_in,
        last_out=last_out,
        worked_minutes=worked_minutes,
        break_minutes=max(0, span_minutes - worked_minutes),
    )


def minutes_between(start: datetime, end: datetime) -> int:
    """Whole minutes from ``start`` to ``end`` (floored, never negative)."""
    return max(0, int((end - start).total_seconds() // 60))


def scheduled_minutes(
    *,
    timetable,
    expected_in: datetime | None,
    expected_out: datetime | None,
    breaks=None,
) -> int:
    """Minutes the employee is expected to work on the day.

    Span between ``expected_in/out`` minus unpaid break overlap. Breaks
    are assumed on the check-in day (overnight shifts included). When
    there are no fixed times (flexible timetable), falls back to
    ``timetable.work_minutes`` (or 0).
    """
    if expected_in is None or expected_out is None:
        return max(0, timetable.work_minutes or 0)
    span = minutes_between(expected_in, expected_out)
    if getattr(timetable, "count_break_time_as_work_time", False):
        return span
    if breaks is None:
        breaks = timetable.breaks.all()
    span_days = (expected_out.date() - expected_in.date()).days
    unpaid = 0
    for b in breaks:
        # A break's wall-clock window can fall on any calendar day the
        # shift span touches (e.g. a 02:00 break on a 22:00 -> 06:00
        # night shift). Score every candidate occurrence and keep the
        # best overlap so each break counts exactly once.
        best = 0
        for offset in range(-1, span_days + 2):
            day = (expected_in + timedelta(days=offset)).date()
            start = timezone.make_aware(datetime.combine(day, b.start_time))
            end = timezone.make_aware(datetime.combine(day, b.end_time))
            if end <= start:
                continue
            overlap = minutes_between(
                max(expected_in, start), min(expected_out, end)
            )
            best = max(best, overlap)
        if getattr(b, "break_time_type", "fixed") == "flexible":
            best = min(best, b.break_time_minutes or 0)
        unpaid += best
    return max(0, span - unpaid)


class DayVariances(NamedTuple):
    """Late / early / overtime minutes for one day."""

    late_minutes: int
    early_minutes: int
    overtime_minutes: int


def day_variances(
    *,
    first_in: datetime | None,
    last_out: datetime | None,
    worked_minutes: int,
    expected_in: datetime | None,
    expected_out: datetime | None,
    scheduled: int,
    late_grace_minutes: int = 0,
    early_grace_minutes: int = 0,
) -> DayVariances:
    """Compare actual punches against expected times.

    Grace is subtracted after the raw difference (callers map
    ``Timetable.grace_period_minutes`` / ``grace_period_check_out`` to
    these two arguments). Overtime is worked time beyond scheduled
    minutes.
    """
    late = (
        max(
            0,
            minutes_between(expected_in, first_in) - max(0, late_grace_minutes),
        )
        if expected_in is not None and first_in is not None
        else 0
    )
    early = (
        max(
            0,
            minutes_between(last_out, expected_out)
            - max(0, early_grace_minutes),
        )
        if expected_out is not None and last_out is not None
        else 0
    )
    return DayVariances(
        late_minutes=late,
        early_minutes=early,
        overtime_minutes=max(0, worked_minutes - scheduled),
    )
