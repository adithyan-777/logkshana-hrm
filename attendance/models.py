from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from common.models import BaseModel

# ============================================================
# ATTENDANCE TRANSACTION
# ============================================================


class AttendanceTransaction(BaseModel):
    """
    Normalized/raw attendance punch.

    This model is provider-agnostic. Provider-specific information
    should be stored by the integration layer and/or in raw_data.

    Example providers:
        - ZKTeco BioTime
        - Suprema
        - Hikvision
        - Anviz
    """

    class Direction(models.TextChoices):
        IN = "in", "Check In"
        OUT = "out", "Check Out"
        UNKNOWN = "unknown", "Unknown"

    class Source(models.TextChoices):
        BIOMETRIC = "biometric", "Biometric"
        WEB = "web", "Web"
        MOBILE = "mobile", "Mobile"
        MANUAL = "manual", "Manual"
        IMPORT = "import", "Import"

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="attendance_transactions",
    )

    # ID supplied by the external provider.
    external_id = models.CharField(
        max_length=255,
    )

    timestamp = models.DateTimeField()

    direction = models.CharField(
        max_length=20,
        choices=Direction.choices,
        default=Direction.UNKNOWN,
    )

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.BIOMETRIC,
    )

    # Optional provider/user information.
    external_employee_id = models.CharField(
        max_length=255,
        blank=True,
    )

    # Keep the original provider payload.
    raw_data = models.JSONField(
        default=dict,
        blank=True,
    )

    class Meta:
        ordering = ["-timestamp"]

        indexes = [
            models.Index(
                fields=["employee", "timestamp"],
            ),
        ]

    def __str__(self):
        return f"{self.employee} - {self.timestamp}"


# ============================================================
# ATTENDANCE PERIOD
# ============================================================


class AttendancePeriod(BaseModel):
    """
    A matched IN -> OUT working period.

    Example:

        09:00 -> 13:00
        14:00 -> 18:00

    produces two periods.
    """

    daily_attendance = models.ForeignKey(
        "DailyAttendance",
        on_delete=models.CASCADE,
        related_name="periods",
    )

    check_in = models.ForeignKey(
        AttendanceTransaction,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="check_in_periods",
    )

    check_out = models.ForeignKey(
        AttendanceTransaction,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="check_out_periods",
    )

    worked_minutes = models.PositiveIntegerField(
        default=0,
    )

    is_valid = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["check_in"]


# ============================================================
# DAILY ATTENDANCE
# ============================================================


class DailyAttendance(BaseModel):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EARLY_OUT = "early_out", "Early Out"
        INCOMPLETE = "incomplete", "Incomplete"
        DAY_OFF = "day_off", "Day Off"
        HOLIDAY = "holiday", "Holiday"
        LEAVE = "leave", "Leave"
        WORKED_HOLIDAY = "worked_holiday", "Worked Holiday"
        OVERTIME = "overtime", "Overtime"

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="daily_attendance",
    )

    date = models.DateField()

    # --------------------------------------------------------
    # Schedule used for calculation
    # --------------------------------------------------------

    shift = models.ForeignKey(
        "schedule.Shift",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="attendance_results",
    )

    timetable = models.ForeignKey(
        "schedule.Timetable",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="attendance_results",
    )

    # --------------------------------------------------------
    # Expected working time
    # --------------------------------------------------------

    expected_in = models.DateTimeField(
        null=True,
        blank=True,
    )

    expected_out = models.DateTimeField(
        null=True,
        blank=True,
    )

    scheduled_minutes = models.PositiveIntegerField(
        default=0,
    )

    # --------------------------------------------------------
    # Actual working time
    # --------------------------------------------------------

    first_in = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_out = models.DateTimeField(
        null=True,
        blank=True,
    )

    worked_minutes = models.PositiveIntegerField(
        default=0,
    )

    break_minutes = models.PositiveIntegerField(
        default=0,
    )

    # --------------------------------------------------------
    # Attendance calculations
    # --------------------------------------------------------

    late_minutes = models.PositiveIntegerField(
        default=0,
    )

    early_leave_minutes = models.PositiveIntegerField(
        default=0,
    )

    overtime_minutes = models.PositiveIntegerField(
        default=0,
    )

    absent_minutes = models.PositiveIntegerField(
        default=0,
    )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PRESENT,
    )

    has_check_in = models.BooleanField(
        default=False,
    )

    has_check_out = models.BooleanField(
        default=False,
    )

    # --------------------------------------------------------
    # Calculation metadata
    # --------------------------------------------------------

    is_calculated = models.BooleanField(
        default=False,
    )

    calculated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    calculation_version = models.PositiveIntegerField(
        default=1,
    )

    notes = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["-date"]

        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"],
                name="unique_employee_attendance_day",
            )
        ]

        indexes = [
            models.Index(
                fields=["employee", "date"],
            ),
            models.Index(
                fields=["date", "status"],
            ),
        ]

    def __str__(self):
        return f"{self.employee} - {self.date}"


# ============================================================
# ATTENDANCE CORRECTION
# ============================================================


class AttendanceCorrection(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="attendance_corrections",
    )

    date = models.DateField()

    check_in = models.DateTimeField(
        null=True,
        blank=True,
    )

    check_out = models.DateTimeField(
        null=True,
        blank=True,
    )

    reason = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_corrections_requested",
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_corrections_approved",
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )


# ============================================================
# OVERTIME
# ============================================================


class OvertimeRecord(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        AUTO_APPROVED = "auto_approved", "Auto Approved"

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="overtime_records",
    )

    date = models.DateField()

    daily_attendance = models.ForeignKey(
        DailyAttendance,
        on_delete=models.CASCADE,
        related_name="overtime_records",
    )

    start_time = models.DateTimeField(
        null=True,
        blank=True,
    )

    end_time = models.DateTimeField(
        null=True,
        blank=True,
    )

    minutes = models.PositiveIntegerField(
        default=0,
    )

    reason = models.TextField(
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="overtime_requested",
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="overtime_approved",
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )


# ============================================================
# ATTENDANCE RULES
# ============================================================


class AttendanceRule(BaseModel):
    name = models.CharField(
        max_length=100,
    )

    # --------------------------------------------------------
    # Missing punches
    # --------------------------------------------------------

    require_check_in = models.BooleanField(
        default=True,
    )

    require_check_out = models.BooleanField(
        default=True,
    )

    missing_check_in_as_absence = models.BooleanField(
        default=True,
    )

    missing_check_out_as_incomplete = models.BooleanField(
        default=True,
    )

    # --------------------------------------------------------
    # Late / early
    # --------------------------------------------------------

    late_grace_minutes = models.PositiveIntegerField(
        default=0,
    )

    early_leave_grace_minutes = models.PositiveIntegerField(
        default=0,
    )

    late_to_absence_minutes = models.PositiveIntegerField(
        default=0,
    )

    # --------------------------------------------------------
    # Punch handling
    # --------------------------------------------------------

    duplicate_punch_window_minutes = models.PositiveIntegerField(
        default=1,
    )

    allow_multiple_in_out = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        verbose_name = "Attendance rule"
        verbose_name_plural = "Attendance rules"


# ============================================================
# CALCULATION RUN
# ============================================================


class AttendanceCalculationRun(BaseModel):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    start_date = models.DateField()

    end_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
    )

    employees_count = models.PositiveIntegerField(
        default=0,
    )

    records_processed = models.PositiveIntegerField(
        default=0,
    )

    records_created = models.PositiveIntegerField(
        default=0,
    )

    records_updated = models.PositiveIntegerField(
        default=0,
    )

    error_count = models.PositiveIntegerField(
        default=0,
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    error_message = models.TextField(
        blank=True,
    )
