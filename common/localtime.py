"""Timezone helpers for the naive-Asia/Qatar operating mode.

With ``USE_TZ = False`` Django stores and returns naive wall-clock
values (session timezone = ``TIME_ZONE``), so the wall clock is just
``.day``/``.date()`` — but a few defensive paths (legacy aware values,
settings-flipped environments) may still hand us aware datetimes, where
``timezone.localtime`` is the only correct conversion.
"""
from django.utils import timezone


def local_date(value=None):
    """Date in the active timezone; works for naive and aware values."""
    value = timezone.now() if value is None else value
    if timezone.is_naive(value):
        return value.date()
    return timezone.localtime(value).date()


def local_dt(value):
    """Wall-clock datetime in the active timezone; naive stays as-is."""
    if timezone.is_naive(value):
        return value
    return timezone.localtime(value)
