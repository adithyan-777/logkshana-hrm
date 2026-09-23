from datetime import date, datetime, timedelta

from django.utils import timezone

from schedule.models import Timetable


def expected_datetimes(
    *,
    timetable: Timetable,
    day: date,
) -> tuple[datetime | None, datetime | None]:
    """
    Expected check-in/check-out datetimes for a timetable on `day`.

    Check-in falls on `day`; the cross-day offset moves check-out
    forward by whole days, so a night shift (22:00 -> 06:00 with
    check_out_cross_days=1) on Monday expects its check-out early on
    Tuesday.

    Returns (None, None) for timetables without fixed times
    (e.g. flexible timetables without times).
    """
    if timetable.check_in is None and timetable.check_out is None:
        return None, None

    expected_in = None
    if timetable.check_in is not None:
        expected_in = timezone.make_aware(
            datetime.combine(day, timetable.check_in)
        )

    expected_out = None
    if timetable.check_out is not None:
        expected_out = timezone.make_aware(
            datetime.combine(
                day + timedelta(days=timetable.check_out_cross_days or 0),
                timetable.check_out,
            )
        )

    return expected_in, expected_out
