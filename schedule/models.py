from django.core.validators import MinValueValidator
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

    class WorkType(models.TextChoices):
        WORK = "work", "Work"
        OFF = "off", "Day Off"
        OVERTIME = "overtime", "Overtime"

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)

    type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.NORMAL,
    )

    # Normal timetable
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)

    # Flexible timetable
    work_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Required working minutes for flexible timetable.",
    )

    work_type = models.CharField(
        max_length=20,
        choices=WorkType.choices,
        default=WorkType.WORK,
    )

    # How many workdays this timetable represents.
    workday = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1,
    )

    # Allowed punch windows
    check_in_start = models.TimeField(null=True, blank=True)
    check_in_end = models.TimeField(null=True, blank=True)

    check_out_start = models.TimeField(null=True, blank=True)
    check_out_end = models.TimeField(null=True, blank=True)

    # Cross-day shift.
    # 0 = same day, 1 = next day, etc.
    check_in_cross_days = models.PositiveSmallIntegerField(default=0)

    check_out_cross_days = models.PositiveSmallIntegerField(default=0)

    # Attendance rules
    require_check_in = models.BooleanField(default=True)
    require_check_out = models.BooleanField(default=True)

    allow_late_in = models.BooleanField(default=False)
    allow_early_out = models.BooleanField(default=False)

    late_in_grace_minutes = models.PositiveIntegerField(default=0)
    early_out_grace_minutes = models.PositiveIntegerField(default=0)

    # Attendance calculation
    multiple_in_out = models.BooleanField(default=False)

    day_change_time = models.TimeField(
        default="08:00",
        help_text="Punches before this time may belong to the previous attendance day.",
    )

    color = models.CharField(
        max_length=20,
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                name="unique_timetable_code",
            )
        ]

    def __str__(self):
        return self.name


class TimetableBreak(BaseModel):
    """
    Break inside a timetable.

    A timetable can contain multiple breaks.
    """

    timetable = models.ForeignKey(
        Timetable,
        on_delete=models.CASCADE,
        related_name="breaks",
    )

    name = models.CharField(max_length=100)

    start_time = models.TimeField()
    end_time = models.TimeField()

    paid = models.BooleanField(default=False)

    minimum_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["start_time"]

    def __str__(self):
        return f"{self.timetable} - {self.name}"


class OvertimeRule(BaseModel):
    """
    Overtime configuration attached to a timetable.
    """

    timetable = models.OneToOneField(
        Timetable,
        on_delete=models.CASCADE,
        related_name="overtime_rule",
    )

    enabled = models.BooleanField(default=False)

    minimum_minutes = models.PositiveIntegerField(default=0)

    maximum_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    count_early_in = models.BooleanField(default=False)
    count_late_out = models.BooleanField(default=False)

    early_in_minimum_minutes = models.PositiveIntegerField(default=0)
    late_out_minimum_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Overtime rule"
        verbose_name_plural = "Overtime rules"


class Shift(BaseModel):
    """
    A repeating arrangement of timetables.

    Example:

        Day 1 -> Morning
        Day 2 -> Morning
        Day 3 -> Morning
        Day 4 -> Off
        Day 5 -> Off

    or:

        Day 1 -> Morning
        Day 2 -> Evening
        Day 3 -> Night
        Day 4 -> Off
    """

    class CycleUnit(models.TextChoices):
        DAY = "day", "Day"
        WEEK = "week", "Week"
        MONTH = "month", "Month"

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)

    auto_shift = models.BooleanField(
        default=False,
        help_text="Automatically determine the matching timetable.",
    )

    cycle_unit = models.CharField(
        max_length=10,
        choices=CycleUnit.choices,
        default=CycleUnit.WEEK,
    )

    cycle_count = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                name="unique_shift_code",
            )
        ]

    def __str__(self):
        return self.name


class ShiftDay(BaseModel):
    """
    Timetable assignment inside a shift cycle.

    Example weekly shift:

        Monday    -> Morning
        Tuesday   -> Morning
        Wednesday -> Morning
        Thursday  -> Morning
        Friday    -> Morning
        Saturday  -> Off
        Sunday    -> Off
    """

    shift = models.ForeignKey(
        Shift,
        on_delete=models.CASCADE,
        related_name="days",
    )

    day_number = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Position inside the cycle, starting at 1.",
    )

    timetable = models.ForeignKey(
        Timetable,
        on_delete=models.PROTECT,
        related_name="shift_days",
    )

    class Meta:
        ordering = ["day_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["shift", "day_number"],
                name="unique_shift_day",
            )
        ]

    def __str__(self):
        return f"{self.shift} - Day {self.day_number}"


class ScheduleAssignment(BaseModel):
    """
    Assigns a shift to employees for a date range.

    This is the actual employee schedule.
    """

    class AssignmentType(models.TextChoices):
        EMPLOYEE = "employee", "Employee"
        DEPARTMENT = "department", "Department"
        GROUP = "group", "Group"

    assignment_type = models.CharField(
        max_length=20,
        choices=AssignmentType.choices,
    )

    shift = models.ForeignKey(
        Shift,
        on_delete=models.PROTECT,
        related_name="assignments",
    )

    start_date = models.DateField()
    end_date = models.DateField()

    # Keep these nullable initially.
    # Replace with your actual HR models.
    employee = models.ForeignKey(
        "employees.Employee",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="schedule_assignments",
    )

    department = models.ForeignKey(
        "employees.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="schedule_assignments",
    )

    overwrite_existing = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(
                fields=["employee", "start_date", "end_date"],
            ),
            models.Index(
                fields=["start_date", "end_date"],
            ),
        ]


class TemporarySchedule(BaseModel):
    """
    Overrides the normal schedule for specific dates.

    Typical uses:
        - overtime
        - weekend work
        - holiday work
        - temporary shift change
        - special assignment
    """

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="temporary_schedules",
    )

    date = models.DateField()

    timetable = models.ForeignKey(
        Timetable,
        on_delete=models.PROTECT,
        related_name="temporary_schedules",
    )

    # Optional reason for the override.
    reason = models.CharField(
        max_length=255,
        blank=True,
    )

    # If false, this can be used as an additional schedule.
    # If true, it replaces the normal schedule for the day.
    overrides_normal_schedule = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["date"]

        indexes = [
            models.Index(
                fields=["employee", "date"],
            ),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date", "timetable"],
                name="unique_employee_temp_schedule",
            )
        ]
