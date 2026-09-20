from django.core.management.base import BaseCommand
from django_celery_beat.models import IntervalSchedule, PeriodicTask


TASK_NAME = "device-attendance-sync-all"
TASK_PATH = "attendance.tasks.device_attendance_sync_all_task"
DEFAULT_INTERVAL_MINUTES = 5


class Command(BaseCommand):
    help = (
        "Register (or update) the Celery Beat periodic task that pulls "
        "attendance logs from the device gateway for all active devices."
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
            help="Disable the periodic task instead of enabling it.",
        )

    def handle(self, *args, **options):
        minutes = options["minutes"]
        enabled = not options["disable"]

        schedule, created = IntervalSchedule.objects.get_or_create(
            every=minutes,
            period=IntervalSchedule.MINUTES,
        )
        schedule_status = "created" if created else "existing"

        task, created = PeriodicTask.objects.update_or_create(
            name=TASK_NAME,
            defaults={
                "interval": schedule,
                "task": TASK_PATH,
                "enabled": enabled,
            },
        )
        task_status = "created" if created else "updated"

        self.stdout.write(
            f"Interval schedule ({minutes} min): {schedule_status} (id={schedule.id})"
        )
        self.stdout.write(
            f"Periodic task '{TASK_NAME}': {task_status} "
            f"(enabled={task.enabled}, task={TASK_PATH})"
        )
        self.stdout.write(self.style.SUCCESS("Device attendance sync schedule ready."))
