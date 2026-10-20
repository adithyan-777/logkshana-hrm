"""Force-recalculate attendance rows under the new break deduction rules.

Destructive: rows are rewritten from their shift plan + punches via
``recalculate_shift`` (force), so anything computed under the old math
(no break deduction from work time) converges to the current rules.

Run inside one tenant at a time::

    python manage.py backfill_break_deduction --schema demo
    python manage.py backfill_break_deduction --schema demo --from 2026-10-01
    python manage.py backfill_break_deduction --schema demo --employee 5
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from attendance.recalculation import recalculate_shift
from schedule.models import ScheduledShiftDay


class Command(BaseCommand):
    help = (
        "Force-recalculate Attendance rows for a tenant so break time is "
        "deducted from work time per the timetable snapshot's "
        "count_break_time_as_work_time flag."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            required=True,
            help="Tenant schema to backfill (e.g. demo).",
        )
        parser.add_argument(
            "--from",
            dest="date_from",
            type=date.fromisoformat,
            default=None,
            help="Only shifts on/after this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--to",
            dest="date_to",
            type=date.fromisoformat,
            default=None,
            help="Only shifts on/before this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--employee",
            type=int,
            default=None,
            help="Only this employee id.",
        )

    def handle(self, *args, **options):
        if (
            options["date_from"] is not None
            and options["date_to"] is not None
            and options["date_from"] > options["date_to"]
        ):
            raise CommandError("--from is after --to")

        with schema_context(options["schema"]):
            shifts = ScheduledShiftDay.objects.select_related("employee").order_by(
                "employee_id", "day"
            )
            if options["date_from"] is not None:
                shifts = shifts.filter(day__gte=options["date_from"])
            if options["date_to"] is not None:
                shifts = shifts.filter(day__lte=options["date_to"])
            if options["employee"] is not None:
                shifts = shifts.filter(employee_id=options["employee"])

            total = shifts.count()
            if total == 0:
                self.stdout.write("Nothing to backfill.")
                return

            self.stdout.write(f"Recalculating {total} shift rows...")
            done = timed_or = 0
            for shift in shifts.iterator():
                row = recalculate_shift(shift=shift, force=True)
                done += 1
                if row.over_time and row.over_time.total_seconds() > 0:
                    timed_or += 1
                self.stdout.write(
                    f"  {shift.employee_id:>6} {shift.day} -> {row.status:<11}"
                    f" work={row.total_work_time} ot={row.over_time}"
                    f" late={row.late_time} early={row.early_leave_time}"
                )
            self.stdout.write(
                self.style.SUCCESS(f"Backfill done: {done} rows ({timed_or} with overtime).")
            )
