from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

TASK_NAME = "nightly-attendance-fanout"
TASK_FUNC = "attendance.q2_tasks.fanout_daily_attendance"
RUN_HOUR_LOCAL = 1  # 01:00 server-local (Asia/Qatar)


class Command(BaseCommand):
    help = (
        "Register (or update) the django-q2 nightly schedule that fans out "
        "attendance calculation to one task per employee per tenant. "
        "Always writes to the PUBLIC schema (schedules are broker-level)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hour",
            type=int,
            default=RUN_HOUR_LOCAL,
            help="Local hour of the nightly run (default: 1).",
        )
        parser.add_argument(
            "--disable",
            action="store_true",
            help="Disable the schedule instead of enabling it.",
        )

    def handle(self, *args, **options):
        from django_q.models import Schedule

        now = timezone.localtime()
        next_run = now.replace(
            hour=options["hour"], minute=0, second=0, microsecond=0
        )
        if next_run <= now:
            next_run += timedelta(days=1)

        with schema_context(get_public_schema_name()):
            schedule, created = Schedule.objects.update_or_create(
                name=TASK_NAME,
                defaults={
                    "func": TASK_FUNC,
                    "schedule_type": Schedule.DAILY,
                    "repeats": -1,
                    "next_run": next_run,
                },
            )
            if options["disable"]:
                schedule.delete()
                self.stdout.write(f"Schedule '{TASK_NAME}' removed.")
                return

        status = "created" if created else "updated"
        self.stdout.write(
            f"Schedule '{TASK_NAME}': {status} "
            f"(daily ~{options['hour']:02d}:00 local, next_run={next_run.isoformat()})"
        )
        self.stdout.write(self.style.SUCCESS("Attendance fanout schedule ready."))
