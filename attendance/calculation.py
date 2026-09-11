from datetime import date, time, timedelta

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
