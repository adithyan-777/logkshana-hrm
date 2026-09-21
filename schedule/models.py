
from django.db import models

from common.models import BaseModel


class Timetable(BaseModel):
    """
    The smallest unit of a work schedule.

    Example:
        Morning Shift
        Check-in: 09:00
        Check-out: 18:00
        Break: 13:00 - 14:00
    """

    class Type(models.TextChoices):
        NORMAL = "normal", "Normal"
        FLEXIBLE = "flexible", "Flexible"

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, null=True)

    type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.NORMAL,
    )

    check_out_cross_days = models.PositiveBigIntegerField(default=0)
    # Normal timetable
    check_in = models.TimeField()
    check_out = models.TimeField()

    # Flexible timetable
    work_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Required working minutes for flexible timetable.",
    )

    # Allowed punch windows
    check_in_start = models.TimeField(null=True, blank=True)
    check_in_end = models.TimeField(null=True, blank=True)

    grace_period_check_out = models.BooleanField(default=False)
    grace_period_minutes = models.PositiveIntegerField(default=0)

    # Attendance calculation
    count_break_time_as_work_time = models.BooleanField(default=False)
    multiple_in_out = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class TimetableBreak(BaseModel):
    """
    Break inside a timetable.

    A timetable can contain multiple breaks.
    """    

    class BreakType(models.TextChoices):
        FIXED = "fixed", "Fixed"
        FLEXIBLE = "flexible", "Flexible"

    timetable = models.ForeignKey(
        Timetable,
        on_delete=models.CASCADE,
        related_name="breaks",
    )

    name = models.CharField(max_length=100)
    break_time_type = models.CharField(
        max_length=10,
        choices=BreakType.choices,
        default=BreakType.FIXED,
    )
    break_time_minutes = models.PositiveIntegerField(null=True, blank=True)

    grace_period_check_out = models.BooleanField(default=False)
    grace_period_minutes = models.PositiveIntegerField(default=0)

    start_time = models.TimeField()
    end_time = models.TimeField()

    def __str__(self):
        return f"{self.timetable} - {self.name}"


class Schedule(BaseModel):

    class RepeatUnitType(models.TextChoices):
        WEEK = "week", "Week"
        MONTH = "month", "Month"
        YEAR = "year", "Year"

    name = models.CharField(max_length=100)
    timetable = models.ForeignKey(
        Timetable,
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    repeat = models.BooleanField(default=True)
    repeat_every = models.PositiveIntegerField(default=1)
    repeat_unit = models.CharField(
        max_length=10,
        choices=RepeatUnitType.choices,
        default=RepeatUnitType.WEEK,
    )
