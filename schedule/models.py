from django.db import models

# Create your models here.
"""
schedule/models.py

Models thin by design (HackSoft styleguide): validation lives in clean(),
business logic (get_effective_shift, logical_date resolution, etc.) lives
in schedule/selectors.py and attendance/services.py — not here.

Tenancy: Timetable, BreakTime, and Shift are org-owned config objects with
no natural parent to inherit scope from, so they carry an explicit
`company` FK. Assignment models (DepartmentShiftAssignment,
GroupShiftAssignment, EmployeeShiftAssignment, TemporaryShiftAssignment)
do NOT carry their own `company` FK — they scope implicitly through the
department/group/employee FK, per project convention.

Cross-day handling: `Timetable.day_change_time` is the single authoritative
cutover used everywhere a punch needs to be bucketed into a logical day.
Never infer "night shift" from check_out < check_in — use the explicit
*_day_offset fields instead. This is deliberately closer to BioTime's
design than to Frappe HR's inferred-from-time-comparison approach, because
it survives split/broken shifts where start/end order tells you nothing.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

# from logkshana.common.models import BaseModel  # created_at/updated_at + full_clean()-on-save

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class TimetableType(models.TextChoices):
    NORMAL = "NORMAL", "Normal"
    FLEXIBLE = "FLEXIBLE", "Flexible"


class BreakCalculationType(models.TextChoices):
    AUTO_DEDUCT = "AUTO_DEDUCT", "Auto Deduct"
    REQUIRED_PUNCH = "REQUIRED_PUNCH", "Required Punch"


class DuplicatePunchPolicy(models.TextChoices):
    RULE_BASED = "RULE_BASED", "Rule Based"
    USER_DEFINED = "USER_DEFINED", "User Defined"


class PairingRule(models.TextChoices):
    FIRST_AND_LAST = "FIRST_AND_LAST", "First And Last"
    ODD_EVEN = "ODD_EVEN", "Odd Even"
    PUNCH_STATE_BASED = "PUNCH_STATE_BASED", "Punch State Based"


class CycleUnit(models.TextChoices):
    DAY = "DAY", "Day"
    WEEK = "WEEK", "Week"
    MONTH = "MONTH", "Month"


class ShiftScopeType(models.TextChoices):
    DEPARTMENT = "DEPARTMENT", "Department"
    GROUP = "GROUP", "Group"
    EMPLOYEE = "EMPLOYEE", "Employee"


# ---------------------------------------------------------------------------
# Break Time
# ---------------------------------------------------------------------------

class BreakTime(BaseModel):
    """A reusable break-time block. Attached to one or more Timetables."""

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="break_times"
    )
    name = models.CharField(max_length=50)

    calculation_type = models.CharField(
        max_length=20, choices=BreakCalculationType.choices
    )

    start_time = models.TimeField()
    end_time = models.TimeField()
    duration_minutes = models.PositiveSmallIntegerField()

    duplicate_punch_policy = models.CharField(
        max_length=20, choices=DuplicatePunchPolicy.choices,
        default=DuplicatePunchPolicy.RULE_BASED,
    )
    duplicate_punch_interval_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Required when duplicate_punch_policy = USER_DEFINED.",
    )
    punch_state_based = models.BooleanField(default=False)

    allow_multiple_in_out = models.BooleanField(default=False)
    minimum_break_minutes = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_breaktime_name_per_company"
            ),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.start_time} - {self.end_time})"

    def clean(self):
        if (
            self.duplicate_punch_policy == DuplicatePunchPolicy.USER_DEFINED
            and self.duplicate_punch_interval_minutes is None
        ):
            raise ValidationError(
                "duplicate_punch_interval_minutes is required when "
                "duplicate_punch_policy is USER_DEFINED."
            )


# ---------------------------------------------------------------------------
# Timetable
# ---------------------------------------------------------------------------

class Timetable(BaseModel):
    """
    The atomic daily-behavior definition. NOT the assignable unit —
    Shift is the assignable unit and composes one or more Timetables
    across a cycle. See ShiftTimetableAssignment.
    """

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="timetables"
    )
    name = models.CharField(max_length=50)
    timetable_type = models.CharField(
        max_length=10, choices=TimetableType.choices, default=TimetableType.NORMAL
    )

    # --- Punch windows -----------------------------------------------------
    # *_day_offset is explicit (0-3), never inferred from time comparison.
    # This is the core departure from Frappe HR's "end_time < start_time"
    # heuristic, and it's what survives split/broken shifts.
    check_in_start_time = models.TimeField()
    check_in_start_day_offset = models.PositiveSmallIntegerField(default=0)
    check_in_end_time = models.TimeField()
    check_in_end_day_offset = models.PositiveSmallIntegerField(default=0)

    check_out_start_time = models.TimeField()
    check_out_start_day_offset = models.PositiveSmallIntegerField(default=0)
    check_out_end_time = models.TimeField()
    check_out_end_day_offset = models.PositiveSmallIntegerField(default=0)

    check_in_time = models.TimeField()
    check_in_day_offset = models.PositiveSmallIntegerField(default=0)
    check_out_time = models.TimeField()
    check_out_day_offset = models.PositiveSmallIntegerField(default=0)

    # --- Day boundary --------------------------------------------------
    # Authoritative cutover for bucketing punches into a logical day.
    # Everything in `attendance` reads this — never a raw punch timestamp.
    day_change_time = models.TimeField(
        help_text="Punches before this time belong to the previous logical day."
    )

    # Cached/derived — not authoritative on its own, recomputed in clean()/save().
    # Purely a query optimization so list views don't recompute offset arithmetic.
    is_cross_day = models.BooleanField(default=False, editable=False)

    # --- Basic setting -------------------------------------------------
    workday_value = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True,
        help_text="Overrides attendance-rule workday calculation when set.",
    )
    color = models.CharField(max_length=7, blank=True, help_text="Hex color for reports.")

    break_times = models.ManyToManyField(
        BreakTime, blank=True, related_name="timetables"
    )

    # --- Unscheduled time (early-in / late-out) -------------------------
    early_in_enabled = models.BooleanField(default=False)
    early_in_minimum_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    early_in_count_minimum = models.BooleanField(default=True)
    early_in_pay_code = models.ForeignKey(
        "attendance.PayCode", on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )

    late_out_enabled = models.BooleanField(default=False)
    late_out_minimum_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    late_out_count_minimum = models.BooleanField(default=True)
    late_out_pay_code = models.ForeignKey(
        "attendance.PayCode", on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )

    # --- Overtime rule ----------------------------------------------------
    max_overtime_minutes = models.PositiveIntegerField(null=True, blank=True)

    # --- Rule setting -------------------------------------------------
    clock_in_required = models.BooleanField(default=True)
    clock_out_required = models.BooleanField(default=True)
    allow_late_in_minutes = models.PositiveSmallIntegerField(default=0)
    allow_early_out_minutes = models.PositiveSmallIntegerField(default=0)

    duplicate_punch_policy = models.CharField(
        max_length=20, choices=DuplicatePunchPolicy.choices,
        default=DuplicatePunchPolicy.RULE_BASED,
    )
    duplicate_punch_interval_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True
    )
    punch_state_based = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_timetable_name_per_company"
            ),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        if (
            self.duplicate_punch_policy == DuplicatePunchPolicy.USER_DEFINED
            and self.duplicate_punch_interval_minutes is None
        ):
            raise ValidationError(
                "duplicate_punch_interval_minutes is required when "
                "duplicate_punch_policy is USER_DEFINED."
            )
        self.is_cross_day = any(
            offset > 0
            for offset in (
                self.check_in_start_day_offset,
                self.check_in_end_day_offset,
                self.check_out_start_day_offset,
                self.check_out_end_day_offset,
                self.check_in_day_offset,
                self.check_out_day_offset,
            )
        )


class TimetableOvertimeLevel(BaseModel):
    """Up to 3 ordered OT levels per Timetable, matching BioTime's OT1-3."""

    timetable = models.ForeignKey(
        Timetable, on_delete=models.CASCADE, related_name="overtime_levels"
    )
    level_number = models.PositiveSmallIntegerField()
    work_hours_from = models.DecimalField(max_digits=4, decimal_places=2)
    work_hours_to = models.DecimalField(max_digits=4, decimal_places=2)
    pay_code = models.ForeignKey(
        "attendance.PayCode", on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["timetable", "level_number"],
                name="uniq_ot_level_per_timetable",
            ),
        ]
        ordering = ["timetable", "level_number"]

    def __str__(self) -> str:
        return f"{self.timetable.name} OT{self.level_number}"

    def clean(self):
        if not 1 <= self.level_number <= 3:
            raise ValidationError("level_number must be between 1 and 3.")
        if self.work_hours_from >= self.work_hours_to:
            raise ValidationError("work_hours_from must be less than work_hours_to.")


# ---------------------------------------------------------------------------
# Shift — the assignable unit, composed of Timetables across a cycle
# ---------------------------------------------------------------------------

class Shift(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="shifts"
    )
    name = models.CharField(max_length=50)

    auto_shift = models.BooleanField(
        default=False,
        help_text="If enabled, interleaved/overlapping timetable periods are allowed.",
    )
    cycle_unit = models.CharField(max_length=5, choices=CycleUnit.choices)
    cycle_count = models.PositiveSmallIntegerField(
        help_text="Cycle period = cycle_count * cycle_unit."
    )

    timetables = models.ManyToManyField(
        Timetable, through="ShiftTimetableAssignment", related_name="shifts"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_shift_name_per_company"
            ),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ShiftTimetableAssignment(BaseModel):
    """Maps which Timetable applies to which day-position within a Shift's cycle."""

    shift = models.ForeignKey(
        Shift, on_delete=models.CASCADE, related_name="timetable_assignments"
    )
    timetable = models.ForeignKey(
        Timetable, on_delete=models.PROTECT, related_name="shift_assignments"
    )
    day_index_in_cycle = models.PositiveSmallIntegerField(
        help_text="0-based position of this timetable within the shift's cycle."
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["shift", "day_index_in_cycle"],
                name="uniq_day_index_per_shift",
            ),
        ]
        ordering = ["shift", "day_index_in_cycle"]

    def __str__(self) -> str:
        return f"{self.shift.name} day {self.day_index_in_cycle} → {self.timetable.name}"

    def clean(self):
        cycle_days = {
            CycleUnit.DAY: 1,
            CycleUnit.WEEK: 7,
            CycleUnit.MONTH: 31,
        }[self.shift.cycle_unit] * self.shift.cycle_count
        if self.day_index_in_cycle >= cycle_days:
            raise ValidationError(
                f"day_index_in_cycle must be within the shift's "
                f"{cycle_days}-day cycle."
            )


# ---------------------------------------------------------------------------
# Assignment models — resolution priority (highest first):
# TemporaryShiftAssignment > EmployeeShiftAssignment >
# GroupShiftAssignment > DepartmentShiftAssignment
# Enforced in schedule/selectors.py:get_effective_shift(), not here.
# ---------------------------------------------------------------------------

class DepartmentShiftAssignment(BaseModel):
    department = models.ForeignKey(
        "employees.Department", on_delete=models.CASCADE, related_name="shift_assignments"
    )
    shift = models.ForeignKey(
        Shift, on_delete=models.PROTECT, related_name="department_assignments"
    )
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["department", "start_date", "end_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.department} → {self.shift} ({self.start_date}–{self.end_date})"

    def clean(self):
        if self.start_date > self.end_date:
            raise ValidationError("start_date must not be after end_date.")


class GroupShiftAssignment(BaseModel):
    attendance_group = models.ForeignKey(
        "employees.AttendanceGroup", on_delete=models.CASCADE, related_name="shift_assignments"
    )
    shift = models.ForeignKey(
        Shift, on_delete=models.PROTECT, related_name="group_assignments"
    )
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["attendance_group", "start_date", "end_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.attendance_group} → {self.shift} ({self.start_date}–{self.end_date})"

    def clean(self):
        if self.start_date > self.end_date:
            raise ValidationError("start_date must not be after end_date.")


class EmployeeShiftAssignment(BaseModel):
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="shift_assignments"
    )
    shift = models.ForeignKey(
        Shift, on_delete=models.PROTECT, related_name="employee_assignments"
    )
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["employee", "start_date", "end_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee} → {self.shift} ({self.start_date}–{self.end_date})"

    def clean(self):
        if self.start_date > self.end_date:
            raise ValidationError("start_date must not be after end_date.")


class TemporaryShiftAssignment(BaseModel):
    """
    Single-date override, highest priority in resolution. May override with
    either a full Shift or a bare Timetable for that one date — BioTime
    supports both entry points (Temporary Schedule can target either).
    """

    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE,
        related_name="temporary_shift_assignments",
    )
    date = models.DateField()
    shift = models.ForeignKey(
        Shift, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    timetable = models.ForeignKey(
        Timetable, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"], name="uniq_temp_assignment_per_employee_date"
            ),
        ]
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.employee} temp override on {self.date}"

    def clean(self):
        if not self.shift and not self.timetable:
            raise ValidationError("Either shift or timetable must be set.")
        if self.shift and self.timetable:
            raise ValidationError("Set only one of shift or timetable, not both.")