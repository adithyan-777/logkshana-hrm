"""Small pure helpers for attendance ingest and arithmetic.

Gateway direction mapping and whole-minute arithmetic live here; the
daily Attendance calculation is being rewritten and does not exist yet.
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

GATEWAY_STATUS_MAPPING ={
    "in": "Check In",
    "out": "Check Out",
    "checkin": "Check In",
    "checkout": "Check Out"
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


def _clean_status_label(value) -> str:
    return (
        str(value).strip().replace("-", " ").replace("_", "").replace(" ", "").lower()
    )


def direction_from_gateway_status_label(status_label) -> str:
    status = "unknown"
    if not status_label:
        return status
    cleaned_label = _clean_status_label(status_label)
    for key, label in GATEWAY_STATUS_MAPPING.items():
        if cleaned_label in (_clean_status_label(key), _clean_status_label(label)):
            return "out" if "out" in key else "in"
    return status


def minutes_between(start: datetime, end: datetime) -> int:
    """Whole minutes from ``start`` to ``end`` (floored, never negative)."""
    return max(0, int((end - start).total_seconds() // 60))
