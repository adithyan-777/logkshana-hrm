
from datetime import date, datetime, timedelta
from datetime import time as dt_time

from django.core.exceptions import ValidationError
from django.db import models

from common.models import BaseModel
from employees.models import Employee

TIMETABLE_TIMES_ORDER_ERROR = (
    "Check-out must be after check-in. For an overnight shift "
    "(e.g. 22:00 to 06:00), set check-out cross days to 1."
)

BREAK_OUTSIDE_WORK_ERROR = (
    "Break must be within working hours (check-in to check-out)."
)


def validate_timetable_times(
    *,
    check_in,
    check_out,
    check_out_cross_days,
) -> None:
    """
    Check-out must land strictly after check-in on the effective
    timeline (check-out offset by its cross-day value), so 22:00 ->
    06:00 is only valid with check_out_cross_days >= 1.

    Missing times or cross-day values are skipped here; field-level
    validation reports them.
    """
    if check_in is None or check_out is None:
        return
    if check_out_cross_days is None:
        return

    # Compare on a timeline anchored to one date, offset by the
    # cross-day field.
    anchor = date(2000, 1, 1)
    effective_in = datetime.combine(anchor, check_in)
    effective_out = datetime.combine(
        anchor + timedelta(days=check_out_cross_days),
        check_out,
    )
    if effective_out <= effective_in:
        raise ValidationError({"check_out_cross_days": TIMETABLE_TIMES_ORDER_ERROR})


def validate_break_within_timetable(
    *,
    start_time,
    end_time,
    check_in,
    check_out,
    check_out_cross_days: int = 0,
) -> None:
    """Break window must sit inside the timetable's work window.

    Overnight-aware: with ``check_out_cross_days >= 1`` the work window
    spans midnight, and early-morning breaks are read on the next day.
    Flexible timetables without fixed times are skipped (no window).
    """
    if start_time is None or end_time is None:
        return
    if check_in is None or check_out is None:
        return
    anchor = date(2000, 1, 1)
    work_start = datetime.combine(anchor, check_in)
    work_end = datetime.combine(
        anchor + timedelta(days=check_out_cross_days or 0),
        check_out,
    )
    break_start = datetime.combine(anchor, start_time)
    break_end = datetime.combine(anchor, end_time)
    if break_end <= break_start:
        return  # Reported separately as an ordering error.
    if (check_out_cross_days or 0) and break_start < work_start:
        break_start += timedelta(days=1)
        break_end += timedelta(days=1)
    if break_start < work_start or break_end > work_end:
        raise ValidationError({"start_time": BREAK_OUTSIDE_WORK_ERROR})


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

    def clean(self):
        super().clean()
        validate_timetable_times(
            check_in=self.check_in,
            check_out=self.check_out,
            check_out_cross_days=self.check_out_cross_days,
        )
        # Punches before day_change_time attribute to the previous day,
        # so a check-in punch earlier than it would land on the wrong day.
        if (
            self.check_in is not None
            and self.day_change_time is not None
            and self.day_change_time > self.check_in
        ):
            raise ValidationError(
                {
                    "day_change_time": (
                        "Day change time must not be later than check-in; "
                        "punches before it count toward the previous day."
                    )
                }
            )

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

    start_time = models.TimeField()
    end_time = models.TimeField()

    def clean(self):
        super().clean()
        # Work-window containment is owned by the break formset (fresh
        # parent values) and by timetable_break_create (explicit window);
        # only parent-independent rules live here.
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValidationError(
                {"end_time": "End time must be after start time."}
            )
        if (
            self.break_time_type == TimetableBreak.BreakType.FLEXIBLE
            and self.break_time_minutes is None
        ):
            raise ValidationError(
                {
                    "break_time_minutes": (
                        "Break minutes are required for flexible breaks."
                    )
                }
            )

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
        if (
            self.repeat
            and self.repeat_every is not None
            and self.repeat_every < 1
        ):
            raise ValidationError(
                {"repeat_every": "Repeat interval must be at least 1."}
            )

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

    def clean(self):
        super().clean()
        if (
            self.start_date
            and self.end_date
            and self.end_date < self.start_date
        ):
            raise ValidationError({"end_date": "End date must not be before start date."})

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

    def clean(self):
        super().clean()
        if self.is_day_off and self.schedule_id:
            raise ValidationError(
                {
                    "schedule": (
                        "A day-off override must not point at a schedule."
                    )
                }
            )
        if not self.is_day_off and self.schedule_id is None:
            raise ValidationError(
                {
                    "schedule": (
                        "Choose a schedule for the swap, or mark the day "
                        "as a day off."
                    )
                }
            )

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(
                fields=("employee", "date"),
                name="unique_employee_schedule_override",
            )
        ]
        indexes = [
            # ensure_day looks overrides up by date alone, which the
            # (employee, date) constraint above cannot serve.
            models.Index(fields=["date"], name="sched_override_date_idx"),
        ]


    def __str__(self):
        if self.is_day_off:
            return f"{self.employee} - {self.date} (day off)"
        return f"{self.employee} - {self.date} -> {self.schedule}"
    