from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.models import BaseModel
from schedule.models import ScheduledShiftDay, Timetable


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
        BREAK_IN = 'break_in', 'BREAK IN'
        BREAK_OUT = 'break_out', 'BREAK OUT'
        OVERTIME_IN = 'overtime_in', 'OVERTIME IN'
        OVERTIME_OUT = 'overtime_out', 'OVERTIME OUT'
        UNKNOWN = 'unknown', 'Unknown'

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="attendance_activities",
    )
    scheduled_shift = models.ForeignKey(
        ScheduledShiftDay,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="attendance_activities",
    )
    punch_time = models.DateTimeField()
    direction = models.CharField(
        max_length=12,
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

class WorkSession(BaseModel):
    """One IN/OUT punch pair: a single work visit within a day.

    Derived from AttendanceActivity punches at recalculation time;
    the punch log stays the source of truth. ``check_in``/``check_out``
    are frozen copies of the punch times (they survive punch deletion,
    hence SET_NULL on both punch FKs). ``check_out`` is null while the
    session is still open.
    """

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="work_sessions",
    )
    attendance = models.ForeignKey(
        "Attendance",
        on_delete=models.CASCADE,
        related_name="work_sessions",
    )
    # Local-accrual day the session belongs to (day of the IN punch).
    day = models.DateField()
    in_punch = models.ForeignKey(
        "AttendanceActivity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        # Anonymous reverse access: nothing reverse-queries the session
        # side of a punch (WorkSession is reachable from Attendance).
        related_name="+",
    )
    out_punch = models.ForeignKey(
        "AttendanceActivity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)
    total_time = models.DurationField(blank=True, default=timedelta(0))

    class Meta:
        constraints = [
            # An IN punch can only ever open one work session
            # (re-pairing is idempotent; Postgres allows many NULLs).
            models.UniqueConstraint(
                fields=("in_punch",),
                name="uniq_worksession_in_punch",
            ),
        ]
        indexes = [
            models.Index(
                fields=["employee", "day"],
                name="ws_emp_day_idx",
            ),
            models.Index(fields=["day"], name="ws_day_idx"),
        ]

    def __str__(self):
        end = (
            f"{self.check_out:%H:%M}" if self.check_out else "open"
        )
        return f"{self.employee_id} {self.day} {self.check_in:%H:%M}-{end}"


class BreakSession(BaseModel):
    """One BREAK_IN/BREAK_OUT punch pair inside a work session.

    Breaks only open while a work session is open; the enclosing
    work session may be split by the break. Same semantics as
    WorkSession otherwise: frozen time copies, SET_NULL punch FKs,
    null ``break_out`` while the break is still open.
    """

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="break_sessions",
    )
    attendance = models.ForeignKey(
        "Attendance",
        on_delete=models.CASCADE,
        related_name="break_sessions",
    )
    work_session = models.ForeignKey(
        "WorkSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="break_sessions",
    )
    # Local-accrual day the break belongs to (day of the BREAK_IN).
    day = models.DateField()
    in_punch = models.ForeignKey(
        "AttendanceActivity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    out_punch = models.ForeignKey(
        "AttendanceActivity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    break_in = models.DateTimeField()
    break_out = models.DateTimeField(null=True, blank=True)
    total_time = models.DurationField(blank=True, default=timedelta(0))

    class Meta:
        constraints = [
            # A BREAK_IN punch can only ever open one break session.
            models.UniqueConstraint(
                fields=("in_punch",),
                name="uniq_breaksession_in_punch",
            ),
        ]
        indexes = [
            models.Index(
                fields=["employee", "day"],
                name="bs_emp_day_idx",
            ),
            models.Index(fields=["day"], name="bs_day_idx"),
        ]

    def __str__(self):
        end = (
            f"{self.break_out:%H:%M}" if self.break_out else "open"
        )
        return f"{self.employee_id} {self.day} {self.break_in:%H:%M}-{end}"


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
    total_break_time = models.DurationField(blank=True, default=timedelta(0))
    late_time = models.DurationField(blank=True, default=timedelta(0))
    early_leave_time = models.DurationField(blank=True, default=timedelta(0))

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INCOMPLETE,
    )
    # True once the daily calculation has written this row; hand-made
    # corrections stay False.
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
            models.UniqueConstraint(
                fields=("employee", "day"),
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
        hours, minutes = divmod(self.worked_minutes, 60)
        return f"{hours}h {minutes:02d}m"

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
