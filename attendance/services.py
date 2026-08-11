from django.core.exceptions import ValidationError
from django.db import transaction

from attendance.models import (
    AttendanceCorrection,
    AttendanceRule,
    AttendanceTransaction,
    DailyAttendance,
)


@transaction.atomic
def attendance_transaction_create(
    *,
    employee,
    external_id: str,
    timestamp,
    direction: str,
    source: str,
    external_employee_id: str = "",
    raw_data=None,
) -> AttendanceTransaction:
    punch = AttendanceTransaction(
        employee=employee,
        external_id=external_id,
        timestamp=timestamp,
        direction=direction,
        source=source,
        external_employee_id=external_employee_id,
        raw_data=raw_data or {},
    )
    punch.full_clean()
    punch.save()
    return punch


@transaction.atomic
def daily_attendance_create(
    *,
    employee,
    date,
    status: str,
    shift=None,
    timetable=None,
    scheduled_minutes: int = 0,
    worked_minutes: int = 0,
    late_minutes: int = 0,
    early_leave_minutes: int = 0,
    overtime_minutes: int = 0,
    has_check_in: bool = False,
    has_check_out: bool = False,
    notes: str = "",
) -> DailyAttendance:
    daily = DailyAttendance(
        employee=employee,
        date=date,
        status=status,
        shift=shift,
        timetable=timetable,
        scheduled_minutes=scheduled_minutes,
        worked_minutes=worked_minutes,
        late_minutes=late_minutes,
        early_leave_minutes=early_leave_minutes,
        overtime_minutes=overtime_minutes,
        has_check_in=has_check_in,
        has_check_out=has_check_out,
        notes=notes,
    )
    daily.full_clean()
    daily.save()
    return daily


@transaction.atomic
def attendance_correction_create(
    *,
    employee,
    date,
    reason: str,
    check_in=None,
    check_out=None,
    status: str = AttendanceCorrection.Status.PENDING,
    requested_by=None,
) -> AttendanceCorrection:
    correction = AttendanceCorrection(
        employee=employee,
        date=date,
        reason=reason,
        check_in=check_in,
        check_out=check_out,
        status=status,
        requested_by=requested_by,
    )
    correction.full_clean()
    _validate_attendance_correction(correction)
    correction.save()
    return correction


@transaction.atomic
def attendance_rule_create(
    *,
    name: str,
    require_check_in: bool = True,
    require_check_out: bool = True,
    missing_check_in_as_absence: bool = True,
    missing_check_out_as_incomplete: bool = True,
    late_grace_minutes: int = 0,
    early_leave_grace_minutes: int = 0,
    late_to_absence_minutes: int = 0,
    duplicate_punch_window_minutes: int = 1,
    allow_multiple_in_out: bool = False,
    is_active: bool = True,
) -> AttendanceRule:
    rule = AttendanceRule(
        name=name,
        require_check_in=require_check_in,
        require_check_out=require_check_out,
        missing_check_in_as_absence=missing_check_in_as_absence,
        missing_check_out_as_incomplete=missing_check_out_as_incomplete,
        late_grace_minutes=late_grace_minutes,
        early_leave_grace_minutes=early_leave_grace_minutes,
        late_to_absence_minutes=late_to_absence_minutes,
        duplicate_punch_window_minutes=duplicate_punch_window_minutes,
        allow_multiple_in_out=allow_multiple_in_out,
        is_active=is_active,
    )
    rule.full_clean()
    rule.save()
    return rule


def _validate_attendance_correction(correction: AttendanceCorrection) -> None:
    if correction.check_in and correction.check_out and correction.check_out < correction.check_in:
        raise ValidationError("Check-out must be on or after check-in.")
