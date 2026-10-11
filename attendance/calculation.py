"""Small pure helpers for attendance ingest and arithmetic.

Shift-day math itself lives in ``attendance.recalculation`` (first-in /
last-out over a materialized ``ScheduledShiftDay``); this module keeps
only the pieces the request path still needs: gateway direction mapping
and whole-minute arithmetic.
"""

from datetime import datetime

# ZKTeco ATTLOG punch states. Most devices report every punch as 0
# unless function keys are configured, so only the explicit
# check-out states map to OUT — everything else stays UNKNOWN.
_GATEWAY_OUT_STATUSES = {
    1,  # Check out
    2,  # Break out
    5,  # Overtime out
}


def direction_from_gateway_status(status) -> str:
    """Map a device-gateway punch ``status`` to a punch direction.

    Returns ``"out"`` for explicit check-out states, ``"unknown"``
    otherwise (missing/garbled values included).
    """
    try:
        code = int(status)
    except (TypeError, ValueError):
        return "unknown"
    return "out" if code in _GATEWAY_OUT_STATUSES else "unknown"


def minutes_between(start: datetime, end: datetime) -> int:
    """Whole minutes from ``start`` to ``end`` (floored, never negative)."""
    return max(0, int((end - start).total_seconds() // 60))
