
from datetime import time as dt_time

from django.core.exceptions import ValidationError
from django.db import models

from common.models import BaseModel
from employees.models import Employee


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
    # Nullable so flexible/off timetables can exist without fixed times.
    # schedule/calculation.expected_datetimes returns (None, None) then.
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)

    # Punches before this time belong to the previous attendance day
    # (overnight checkout attribution).
    day_change_time = models.TimeField(
        default=dt_time(8, 0),
        help_text="Punches before this time may belong to the previous attendance day.", 
    )

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
    duplicate_punch_window_minutes = models.PositiveIntegerField(
        default=1,
        help_text="Punches within this many minutes of the previous punch are treated as duplicates.",
    )

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
    """
    A timetable applied over a date range, optionally repeating.

    The repeat anchor is ``start_date``: weekly/monthly repetition is
    computed from it. ``end_date`` null means open-ended.
    Who works this schedule lives on EmployeeScheduleAssignment, not here
    (mirrors Horilla's EmployeeShift + Roster split).
    """

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
    start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Repeat anchor. Null = always active within the assignment range.",
    )
    end_date = models.DateField(null=True, blank=True)
    repeat = models.BooleanField(default=True)
    repeat_every = models.PositiveIntegerField(default=1)
    repeat_unit = models.CharField(
        max_length=10,
        choices=RepeatUnitType.choices,
        default=RepeatUnitType.WEEK,
    )
    is_active = models.BooleanField(default=True)

    def clean(self):
        super().clean()
        if (
            self.start_date
            and self.end_date
            and self.end_date < self.start_date
        ):
            raise ValidationError({"end_date": "End date must not be before start date."})

    def __str__(self):
        return self.name


class EmployeeScheduleAssignment(BaseModel):
    """
    Durable assignment: which employees work which schedule, for when.

    One row covers N employees over one date range (bulk-assign friendly).
    Resolution order for a given (employee, day) is left to the service
    layer, suggested: Override (day off / one-day swap) wins, then the
    active assignment with the highest priority covering that day, then
    most recent start_date as tiebreak.
    """

    name = models.CharField(max_length=100, blank=True, default="")
    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    employees = models.ManyToManyField(
        Employee, related_name="schedule_assignments"
    )
    start_date = models.DateField()
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Null = open-ended.",
    )
    priority = models.IntegerField(
        default=0,
        help_text="Higher wins when assignments overlap on the same day.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-priority", "-start_date"]
        indexes = [
            models.Index(fields=["schedule", "start_date"]),
            models.Index(fields=["start_date", "end_date"]),
        ]


    def __str__(self):
        return self.name or f"Assignment {self.pk} -> {self.schedule}"


class EmployeeScheduleOverride(BaseModel):
    """
    One-day override (Horilla Roster / old TemporarySchedule parity).

    ``schedule`` null + ``is_day_off`` True = week-off / holiday for that
    employee on that date. Otherwise the given schedule replaces whatever
    the durable assignment resolves to.
    """

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="schedule_overrides",
    )
    date = models.DateField()
    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="overrides",
    )
    is_day_off = models.BooleanField(default=False)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(
                fields=("employee", "date"),
                name="unique_employee_schedule_override",
            )
        ]
        indexes = [
            models.Index(fields=["employee", "date"]),
        ]


    def __str__(self):
        if self.is_day_off:
            return f"{self.employee} - {self.date} (day off)"
        return f"{self.employee} - {self.date} -> {self.schedule}"
    