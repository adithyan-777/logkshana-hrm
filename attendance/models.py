from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.models import BaseModel
from schedule.models import Timetable


class AttendanceActivity(BaseModel):
    '''
        Stores activity of the employee lead to attendance.
        Like biometric check in/out or web based check in/out.

        Append-only punch log: one row per punch event, no in/out
        state. Pairing into periods happens at calculation time
        (attendance.calculation), never here.
    '''

    class AttendanceActivityMethodType(models.TextChoices):
        BIOMETRIC = 'biometric', 'Biometric'
        WEB = 'web', 'Web'
        MOBILE = 'mobile', 'Mobile'
        MANUAL = 'manual', 'Manual'
        CORRECTION = 'correction', 'Correction'

    class Direction(models.TextChoices):
        IN = 'in', 'Check In'
        OUT = 'out', 'Check Out'
        UNKNOWN = 'unknown', 'Unknown'

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="attendance_activities",
    )
    punch_time = models.DateTimeField()
    direction = models.CharField(
        max_length=10,
        choices=Direction.choices,
        default=Direction.UNKNOWN,
    )
    method = models.CharField(
        max_length=10,
        choices=AttendanceActivityMethodType.choices,
        default=AttendanceActivityMethodType.BIOMETRIC
    )
    # Original provider payload (status codes, verify mode, ...).
    raw_data = models.JSONField(default=dict, blank=True)

    # The day row this punch was consumed by. Single source of truth
    # for punch -> Attendance linkage (replaces the former M2M plus
    # ``is_attendance_processed`` flag, which could disagree).
    # NULL while the punch is unassigned (no schedule coverage yet).
    attendance = models.ForeignKey(
        "Attendance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
    )
    # Idempotency key for the ingest stream (e.g. gateway:<log_id>,
    # manual:<uuid>). Blank only for legacy hand-entered punches.
    external_id = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("external_id",),
                condition=~Q(external_id=""),
                name="uniq_attendanceactivity_external_id",
            ),
        ]
        indexes = [
            models.Index(
                fields=["employee", "punch_time"],
                name="act_emp_punch_idx",
            ),
            models.Index(fields=["punch_time"], name="act_punch_time_idx"),
        ]

    @property
    def is_attendance_processed(self) -> bool:
        """True once this punch is linked to a written Attendance row.

        Read-only alias kept for admin/tests: it is exactly
        ``attendance_id is not None``, so it can never drift from the
        real linkage.
        """
        return self.attendance_id is not None

    def __str__(self):
        return f"{self.employee_id} {self.punch_time:%Y-%m-%d %H:%M}"


class Attendance(BaseModel):
    """Derived daily summary row for one (employee, day).

    Written by the calculator (``is_calculated=True``) or by hand
    (``is_calculated=False`` — never overwritten without ``force``).
    Every duration is non-null: a write path must set all of them, so
    a stale ``late_time`` can't survive a re-calculation to ABSENT.
    """

    class Status(models.TextChoices):
        PRESENT = 'present', 'Present'
        ABSENT = 'absent', 'Absent'
        LATE = 'late', 'Late'
        EARLY_OUT = 'early_out', 'Early Out'
        INCOMPLETE = 'incomplete', 'Incomplete'
        DAY_OFF = 'day_off', 'Day Off'
        LEAVE = 'leave', 'Leave'
        HOLIDAY = 'holiday', 'Holiday'

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="attendances",
    )
    day = models.DateField()
    shift = models.ForeignKey(
        Timetable,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendances",
    )
    # Frozen copy of the shift parameters that produced these numbers,
    # so editing/deleting a Timetable doesn't rewrite history.
    shift_snapshot = models.JSONField(null=True, blank=True)

    # Persisted boundaries: written once by the calculator, read by
    # reports/templates. No re-pairing (and no queries) on read.
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)

    over_time = models.DurationField(blank=True, default=timedelta(0))
    total_work_time = models.DurationField(blank=True, default=timedelta(0))
    late_time = models.DurationField(blank=True, default=timedelta(0))
    early_leave_time = models.DurationField(blank=True, default=timedelta(0))

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INCOMPLETE,
    )
    # True once the calc job has written this row; hand-made corrections
    # stay False so recalculation never overwrites them.
    is_calculated = models.BooleanField(default=False)
    calculated_at = models.DateTimeField(null=True, blank=True)

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    edit_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            # Partial so a soft-deleted row doesn't block re-creating
            # the same (employee, day).
            models.UniqueConstraint(
                fields=("employee", "day"),
                condition=Q(deleted_at__isnull=True),
                name="unique_employee_attendance_day",
            ),
        ]
        indexes = [
            # The dominant query is "all rows for this day" (day report).
            # A plain (employee, day) index would duplicate the unique
            # constraint above.
            models.Index(fields=["day", "status"], name="att_day_status_idx"),
        ]

    @staticmethod
    def _duration_minutes(value) -> int:
        if value is None:
            return 0
        return int(value.total_seconds() // 60)

    @property
    def first_in(self):
        return self.check_in

    @property
    def last_out(self):
        return self.check_out

    @property
    def has_check_in(self) -> bool:
        return self.check_in is not None

    @property
    def has_check_out(self) -> bool:
        return self.check_out is not None

    @property
    def worked_minutes(self) -> int:
        return self._duration_minutes(self.total_work_time)

    @property
    def worked_hours(self) -> str:
        return f"{round(self.worked_minutes / 60, 2):g}h"

    @property
    def overtime_minutes(self) -> int:
        return self._duration_minutes(self.over_time)

    @property
    def late_minutes(self) -> int:
        return self._duration_minutes(self.late_time)

    @property
    def early_leave_minutes(self) -> int:
        return self._duration_minutes(self.early_leave_time)

    def __str__(self):
        return f"{self.employee_id} {self.day} {self.status}"
