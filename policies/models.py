from datetime import time as dt_time

from django.db import models

from common.models import BaseModel


class AttendancePolicy(BaseModel):
    class ScheduleMode(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled shifts"
        UNSCHEDULED = "unscheduled", "Unscheduled (check-in/check-out only)"

    class AttendancePerDay(models.TextChoices):
        SINGLE = "single", "Single session per day"
        MULTIPLE = "multiple", "Multiple sessions per day"

    schedule_mode = models.CharField(
        max_length=20,
        choices=ScheduleMode.choices,
        default=ScheduleMode.SCHEDULED,
    )

    attendance_per_day = models.CharField(
        max_length=20,
        choices=AttendancePerDay.choices,
        default=AttendancePerDay.SINGLE,
    )


class UnscheduledConfig(BaseModel):
    opening_time = models.TimeField(blank=True, null=True)
    closing_time = models.TimeField(blank=True, null=True)
