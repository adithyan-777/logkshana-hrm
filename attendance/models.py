from django.db import models

from common.models import BaseModel
from schedule.models import Timetable


class AttendanceActivity(BaseModel):

    '''
        Stores activity of the employee lead to attendance.
        Like biometric check in/out or web based check in/out
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
    is_attendance_processed = models.BooleanField(
        default=False,
        help_text="True once this punch is consumed by attendance calculation or entered as a manual correction.",
    )
    # Idempotency key for the ingest stream (e.g. gateway:<log_id>).
    # Blank for hand-entered punches.
    external_id = models.CharField(max_length=255, blank=True, default="")
    # Original provider payload (status codes, verify mode, ...).
    raw_data = models.JSONField(default=dict, blank=True)

    method = models.CharField(max_length=10, 
        choices=AttendanceActivityMethodType.choices,
        default=AttendanceActivityMethodType.BIOMETRIC
    )

class Attendance(BaseModel):
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
    attendance_activities = models.ManyToManyField(
        AttendanceActivity, related_name="attendances"
    )
    shift = models.ForeignKey(
        Timetable,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendances",
    )
    over_time = models.DurationField(blank=True, null=True)
    day = models.DateField()
    total_work_time = models.DurationField(blank=True, null=True)
    late_time = models.DurationField(blank=True, null=True)
    early_leave_time = models.DurationField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PRESENT,
    )
    # True once the calc job has written this row; hand-made corrections
    # stay False so recalculation never overwrites them.
    is_calculated = models.BooleanField(default=False)
    calculated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("employee", "day"),
                name="unique_employee_attendance_day",
            )
        ]
        indexes = [
            models.Index(fields=["employee", "day"]),
        ]

    @staticmethod
    def _duration_minutes(value) -> int:
        if value is None:
            return 0
        return int(value.total_seconds() // 60)

    @property
    def worked_minutes(self) -> int:
        return self._duration_minutes(self.total_work_time)

    @property
    def overtime_minutes(self) -> int:
        return self._duration_minutes(self.over_time)

    @property
    def late_minutes(self) -> int:
        return self._duration_minutes(self.late_time)

    @property
    def early_leave_minutes(self) -> int:
        return self._duration_minutes(self.early_leave_time)

    def _punches(self):
        return list(
            self.attendance_activities.order_by("punch_time", "id"),
        )

    def _effective_boundaries(self):
        """First check-in / last check-out mirroring pairing alternation."""
        first_in = None
        last_out = None
        open_in = False
        for punch in self._punches():
            direction = punch.direction
            if direction not in (
                AttendanceActivity.Direction.IN,
                AttendanceActivity.Direction.OUT,
            ):
                direction = (
                    AttendanceActivity.Direction.OUT
                    if open_in
                    else AttendanceActivity.Direction.IN
                )
            if direction == AttendanceActivity.Direction.IN:
                if first_in is None:
                    first_in = punch.punch_time
                open_in = True
            else:
                last_out = punch.punch_time
                open_in = False
        return first_in, last_out

    @property
    def first_in(self):
        return self._effective_boundaries()[0]

    @property
    def last_out(self):
        return self._effective_boundaries()[1]

    @property
    def has_check_in(self) -> bool:
        return self.first_in is not None

    @property
    def has_check_out(self) -> bool:
        return self.last_out is not None