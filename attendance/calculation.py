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

    ``punches`` must be sorted by timestamp ascending. The first punch
    is always kept (a device double-tap at check-in still counts once).
    """
    kept = []
    window = timedelta(minutes=max(0, window_minutes))
    for punch in punches:
        if kept and punch.timestamp - kept[-1].timestamp <= window:
            continue
        kept.append(punch)
    return kept


def effective_directions(punches) -> list[str]:
    """Resolve one direction per punch for pairing.

    Explicit IN/OUT punches keep their direction; UNKNOWN punches
    alternate (IN when no open check-in, OUT otherwise).
    """
    directions = []
    open_in = False
    for punch in punches:
        direction = punch.direction
        if direction not in ("in", "out"):
            direction = "out" if open_in else "in"
        directions.append(direction)
        open_in = direction == "in"
    return directions


def pair_punches(
    punches,
    *,
    allow_multiple_in_out: bool = False,
) -> list[tuple]:
    """Pair sorted punches into (check_in, check_out) tuples.

    Either side may be None (open period / lone check-out). Pairing is
    positional: consecutive IN -> OUT punches form a period. A second
    IN while one is open closes the previous period as open (invalid)
    when ``allow_multiple_in_out`` is set, otherwise the first
    check-in wins and the repeat is ignored.
    """
    punches = list(punches)
    pairs = []
    pending_in = None
    for punch, direction in zip(punches, effective_directions(punches)):
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
    first_in = next((c.timestamp for c, _ in pairs if c is not None), None)
    last_out = None
    for _, check_out in pairs:
        if check_out is not None:
            last_out = check_out.timestamp
    worked_minutes = sum(
        minutes_between(c.timestamp, o.timestamp)
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
