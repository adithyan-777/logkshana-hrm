"""Backfill auto-ABSENT attendance rows for a date range, across tenants.

The nightly fanout only ever marks the day it runs on, so days missed
before a fix or deploy stay rowless until backfilled. This command
loops tenants × days and calls the same idempotent
``attendance_absent_rows_ensure`` the scheduled path uses.

Usage:
    python manage.py attendance_backfill_absent --from 2026-11-01 --to 2026-11-17
    python manage.py attendance_backfill_absent --from 2026-11-01 \
        --to 2026-11-17 --tenant freshline
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError

MAX_RANGE_DAYS = 400


class Command(BaseCommand):
    help = (
        "Backfill auto-ABSENT attendance rows over an inclusive date "
        "range, for all tenants (or one with --tenant). Idempotent: "
        "rows that already exist are never rewritten."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--from",
            dest="date_from",
            required=True,
            help="ISO start date (inclusive).",
        )
        parser.add_argument(
            "--to",
            dest="date_to",
            required=True,
            help="ISO end date (inclusive).",
        )
        parser.add_argument(
            "--tenant",
            default=None,
            help="Limit to one tenant schema (default: all).",
        )

    def handle(self, *args, **options):
        from django_tenants.utils import schema_context

        from attendance.services import attendance_absent_rows_ensure
        from companies.models import Company

        date_from = date.fromisoformat(options["date_from"])
        date_to = date.fromisoformat(options["date_to"])
        if date_from > date_to:
            raise CommandError("--from must not be after --to.")
        if (date_to - date_from).days > MAX_RANGE_DAYS:
            raise CommandError(
                f"Range too large (> {MAX_RANGE_DAYS} days). Split it."
            )

        tenants = Company.objects.exclude(schema_name="public").order_by(
            "schema_name"
        )
        if options["tenant"]:
            tenants = tenants.filter(schema_name=options["tenant"])
        schemas = list(tenants.values_list("schema_name", flat=True))
        if not schemas:
            raise CommandError("No matching tenants.")

        day = date_from
        totals = {}
        while day <= date_to:
            for schema in schemas:
                with schema_context(schema):
                    created = attendance_absent_rows_ensure(day=day)
                totals[schema] = totals.get(schema, 0) + len(created)
                if created:
                    self.stdout.write(
                        f"{schema} day={day.isoformat()} created={len(created)}"
                    )
            day += timedelta(days=1)

        for schema, total in totals.items():
            self.stdout.write(f"{schema}: {total} absent rows backfilled")
        self.stdout.write(self.style.SUCCESS("Backfill complete."))
