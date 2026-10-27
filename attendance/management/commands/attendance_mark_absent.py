"""Manually run the auto-ABSENT midnight job for one day.

The scheduled path is the dramatiq-crontab fanout
(``attendance.tasks.fanout_mark_absent_for_today``); this command
exists for backfills and testing. Run per tenant schema.
"""

from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Create auto-ABSENT attendance rows for employees with no punches "
        "and no row on the given day (default: today). Runs in the "
        "current (tenant) schema."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--day",
            default=None,
            help="ISO date to mark absent (default: today).",
        )

    def handle(self, *args, **options):
        from attendance.services import attendance_absent_rows_ensure

        day = (
            date.fromisoformat(options["day"]) if options["day"] else timezone.localdate()
        )
        rows = attendance_absent_rows_ensure(day=day)
        self.stdout.write(
            f"day={day.isoformat()} created={len(rows)} "
            f"employees={[row.employee_id for row in rows]}"
        )
        self.stdout.write(self.style.SUCCESS("Auto-absent rows ensured."))
