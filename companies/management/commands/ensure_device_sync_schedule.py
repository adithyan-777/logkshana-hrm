from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

TASK_NAME = "device-attendance-sync"
TASK_FUNC = "attendance.q2_tasks.fanout_device_sync"
DEFAULT_INTERVAL_MINUTES = 5


class Command(BaseCommand):
    help = (
        "Register (or update) the django-q2 schedule that fans out "
        "attendance pulls from the device gateway (one task per active "
        "device). Always writes to the PUBLIC schema (schedules are "
        "broker-level)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=DEFAULT_INTERVAL_MINUTES,
            help=f"Run interval in minutes (default: {DEFAULT_INTERVAL_MINUTES}).",
        )
        parser.add_argument(
            "--disable",
            action="store_true",
            help="Disable the schedule instead of enabling it.",
        )

    def handle(self, *args, **options):
        from django_q.models import Schedule

        minutes = options["minutes"]

        with schema_context(get_public_schema_name()):
            if options["disable"]:
                deleted, _ = Schedule.objects.filter(name=TASK_NAME).delete()
                self.stdout.write(f"Schedule '{TASK_NAME}' removed ({deleted}).")
                return
            schedule, created = Schedule.objects.update_or_create(
                name=TASK_NAME,
                defaults={
                    "func": TASK_FUNC,
                    "schedule_type": Schedule.MINUTES,
                    "minutes": minutes,
                    "repeats": -1,
                    "next_run": timezone.now(),
                },
            )

        status = "created" if created else "updated"
        self.stdout.write(
            f"Schedule '{TASK_NAME}': {status} "
            f"(every {schedule.minutes} min, func={TASK_FUNC})"
        )
        self.stdout.write(self.style.SUCCESS("Device attendance sync schedule ready."))
