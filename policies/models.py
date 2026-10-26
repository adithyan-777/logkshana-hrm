from datetime import time as dt_time

from django.db import models

from common.models import BaseModel


class AttendancePolicy(BaseModel):

    class ScheduleMode(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled shifts"
        UNSCHEDULED = "unscheduled", "Unscheduled (check-in/check-out only)"


    schedule_mode = models.CharField(
        max_length=20,
        choices=ScheduleMode.choices,
        default=ScheduleMode.SCHEDULED,
    )
