"""Dramatiq actors + cron schedules for attendance.

Cron actors must live in this module: dramatiq-crontab's scheduler
(``manage.py crontab``) imports ``<app>.tasks`` for every installed
app, and only decorated actors register.

Every actor carries its tenant ``schema_name`` explicitly and switches
schema itself; the fanout runs against the shared Company model.
"""

import dramatiq
from dramatiq_crontab import cron


@cron("0 0 * * *")  # midnight, scheduler-local time (Asia/Qatar)
@dramatiq.actor
def fanout_mark_absent_for_today():
    """At midnight, enqueue one absent-marking task per tenant.

    Pre-creates ABSENT rows for the day starting; the (future) daily
    calculation flips them as punches land.
    """
    from django.utils import timezone

    from companies.models import Company

    day_iso = timezone.localdate().isoformat()
    for schema_name in (
        Company.objects.exclude(schema_name="public").values_list(
            "schema_name", flat=True
        )
    ):
        mark_absent_for_tenant.send(schema_name, day_iso)
    return {"day": day_iso}


@dramatiq.actor(max_retries=3, min_backoff=60_000, max_backoff=600_000)
def mark_absent_for_tenant(schema_name: str, day_iso: str):
    """Create the auto-ABSENT rows of one tenant for one day."""
    from datetime import date

    from django_tenants.utils import schema_context

    from attendance.services import attendance_absent_rows_ensure

    with schema_context(schema_name):
        created = attendance_absent_rows_ensure(day=date.fromisoformat(day_iso))
    return {
        "schema": schema_name,
        "day": day_iso,
        "created": len(created),
    }
