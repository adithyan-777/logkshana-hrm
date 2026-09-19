from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.calculation import (
    attendance_day_for_punch,
    dedupe_punches,
    direction_from_gateway_status,
    minutes_between,
    pair_punches,
    summarize_pairs,
)
from attendance.integrations.gateway import device_gateway_attendance_fetch
from attendance.models import (
    AttendanceCorrection,
    AttendancePeriod,
    AttendanceRule,
    AttendanceTransaction,
    DailyAttendance,
)
from companies.selectors import device_get_by_serial_number
from employees.models import Employee
from employees.selectors import employee_get_by_emp_code
from employees.services import employee_create
from schedule.calculation import expected_datetimes
from schedule.models import OvertimeRule, Timetable
from schedule.selectors import schedule_for_employee_on_date

DEFAULT_DAY_CHANGE_TIME = time(8, 0)


@transaction.atomic
def attendance_transaction_create(
    *,
    employee,
    external_id: str | None = None,
    timestamp,
    direction: str,
    source: str,
    external_employee_id: str | None = None,
    raw_data=None,
    recalculate: bool = True,
) -> AttendanceTransaction:
    from uuid import uuid4

    if external_employee_id is None:
        external_employee_id = employee.emp_code or ""
    if not external_id:
        external_id = f"manual:{uuid4().hex}"
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
    if recalculate:
        recalculate_daily_attendance_for_punch(
            employee=punch.employee,
            timestamp=punch.timestamp,
        )
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
    if (
        correction.check_in
        and correction.check_out
        and correction.check_out < correction.check_in
    ):
        raise ValidationError("Check-out must be on or after check-in.")


@transaction.atomic
def attendance_transaction_update(
    *,
    transaction: AttendanceTransaction,
    employee,
    external_id: str | None = None,
    timestamp,
    direction: str,
    source: str,
    external_employee_id: str | None = None,
    raw_data=None,
    recalculate: bool = True,
) -> AttendanceTransaction:
    old_employee = transaction.employee
    old_timestamp = transaction.timestamp
    transaction.employee = employee
    # external_id is a stable record identifier: keep the existing one
    # unless an explicit replacement is given. The employee link is
    # always (re-)derived from the employee instance.
    if external_id:
        transaction.external_id = external_id
    if external_employee_id is None:
        external_employee_id = employee.emp_code or ""
    transaction.timestamp = timestamp
    transaction.direction = direction
    transaction.source = source
    transaction.external_employee_id = external_employee_id
    transaction.raw_data = raw_data or {}
    transaction.full_clean()
    transaction.save()
    if recalculate:
        recalculate_daily_attendance_for_punch(
            employee=transaction.employee,
            timestamp=transaction.timestamp,
        )
        if (
            old_employee.pk != transaction.employee.pk
            or old_timestamp != transaction.timestamp
        ):
            recalculate_daily_attendance_for_punch(
                employee=old_employee,
                timestamp=old_timestamp,
            )
    return transaction


@transaction.atomic
def attendance_transaction_delete(
    *, transaction: AttendanceTransaction, recalculate: bool = True
) -> AttendanceTransaction:
    """Soft-deletes the punch (recoverable via all_objects)."""
    employee = transaction.employee
    timestamp = transaction.timestamp
    transaction.delete()
    if recalculate:
        recalculate_daily_attendance_for_punch(
            employee=employee,
            timestamp=timestamp,
        )
    return transaction


@transaction.atomic
def daily_attendance_update(
    *,
    daily_attendance: DailyAttendance,
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
    daily_attendance.employee = employee
    daily_attendance.date = date
    daily_attendance.status = status
    daily_attendance.shift = shift
    daily_attendance.timetable = timetable
    daily_attendance.scheduled_minutes = scheduled_minutes
    daily_attendance.worked_minutes = worked_minutes
    daily_attendance.late_minutes = late_minutes
    daily_attendance.early_leave_minutes = early_leave_minutes
    daily_attendance.overtime_minutes = overtime_minutes
    daily_attendance.has_check_in = has_check_in
    daily_attendance.has_check_out = has_check_out
    daily_attendance.notes = notes
    daily_attendance.full_clean()
    daily_attendance.save()
    return daily_attendance


@transaction.atomic
def daily_attendance_delete(
    *, daily_attendance: DailyAttendance
) -> DailyAttendance:
    """Soft-deletes the daily record (recoverable via all_objects)."""
    daily_attendance.delete()
    return daily_attendance


@transaction.atomic
def attendance_correction_update(
    *,
    correction: AttendanceCorrection,
    employee,
    date,
    reason: str,
    check_in=None,
    check_out=None,
    status: str = AttendanceCorrection.Status.PENDING,
    requested_by=None,
) -> AttendanceCorrection:
    correction.employee = employee
    correction.date = date
    correction.reason = reason
    correction.check_in = check_in
    correction.check_out = check_out
    correction.status = status
    correction.requested_by = requested_by
    correction.full_clean()
    _validate_attendance_correction(correction)
    correction.save()
    return correction


@transaction.atomic
def attendance_correction_delete(
    *, correction: AttendanceCorrection
) -> AttendanceCorrection:
    """Soft-deletes the correction (recoverable via all_objects)."""
    correction.delete()
    return correction


@transaction.atomic
def attendance_rule_update(
    *,
    rule: AttendanceRule,
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
    rule.name = name
    rule.require_check_in = require_check_in
    rule.require_check_out = require_check_out
    rule.missing_check_in_as_absence = missing_check_in_as_absence
    rule.missing_check_out_as_incomplete = missing_check_out_as_incomplete
    rule.late_grace_minutes = late_grace_minutes
    rule.early_leave_grace_minutes = early_leave_grace_minutes
    rule.late_to_absence_minutes = late_to_absence_minutes
    rule.duplicate_punch_window_minutes = duplicate_punch_window_minutes
    rule.allow_multiple_in_out = allow_multiple_in_out
    rule.is_active = is_active
    rule.full_clean()
    rule.save()
    return rule


@transaction.atomic
def attendance_rule_delete(*, rule: AttendanceRule) -> AttendanceRule:
    """Soft-deletes the rule (recoverable via all_objects)."""
    rule.delete()
    return rule


# Short aliases matching the "<entity>_<action>" naming used by URLs/views.
transaction_update = attendance_transaction_update
transaction_delete = attendance_transaction_delete
daily_update = daily_attendance_update
daily_delete = daily_attendance_delete
correction_update = attendance_correction_update
correction_delete = attendance_correction_delete
rule_update = attendance_rule_update
rule_delete = attendance_rule_delete


def resolve_punch_day(*, employee, timestamp):
    """Return the (day, shift, timetable) an attendance punch belongs to.

    Early-morning punches fall on the previous attendance day per the
    timetable's ``day_change_time`` (08:00 when unscheduled), so an
    overnight check-out lands on the day the shift started.
    """
    ts = timestamp
    if timezone.is_naive(ts):
        ts = timezone.make_aware(ts)
    local_date = timezone.localtime(ts).date()
    shift, timetable = schedule_for_employee_on_date(
        employee=employee, day=local_date
    )
    day_change = (
        timetable.day_change_time
        if timetable is not None
        else DEFAULT_DAY_CHANGE_TIME
    )
    day = attendance_day_for_punch(timestamp=ts, day_change_time=day_change)
    if day != local_date:
        prev_shift, prev_timetable = schedule_for_employee_on_date(
            employee=employee, day=day
        )
        if prev_timetable is not None:
            shift, timetable = prev_shift, prev_timetable
    return day, shift, timetable


def recalculate_daily_attendance_for_punch(
    *, employee, timestamp
) -> DailyAttendance | None:
    """Recompute the attendance day a single punch belongs to."""
    day, _, _ = resolve_punch_day(employee=employee, timestamp=timestamp)
    return recalculate_daily_attendance(employee=employee, day=day)


def _unpaid_break_minutes(*, timetable, expected_in, expected_out) -> int:
    total = 0
    for brk in timetable.breaks.all():
        if brk.paid:
            continue
        start = timezone.make_aware(
            datetime.combine(expected_in.date(), brk.start_time)
        )
        end = timezone.make_aware(datetime.combine(expected_in.date(), brk.end_time))
        if end <= start:
            end += timedelta(days=1)
        overlap = min(end, expected_out) - max(start, expected_in)
        total += max(0, int(overlap.total_seconds() // 60))
    return total


def _expected_schedule(*, timetable, day):
    """Return (expected_in, expected_out, scheduled_minutes) for the day.

    Scheduled time is the expected span minus unpaid breaks. Days
    without fixed timetable times carry no expectations.
    """
    if timetable is None:
        return None, None, 0
    expected_in, expected_out = expected_datetimes(timetable=timetable, day=day)
    if expected_in is None or expected_out is None:
        return expected_in, expected_out, 0
    scheduled_minutes = max(
        0,
        minutes_between(expected_in, expected_out)
        - _unpaid_break_minutes(
            timetable=timetable,
            expected_in=expected_in,
            expected_out=expected_out,
        ),
    )
    return expected_in, expected_out, scheduled_minutes


def _overtime_minutes(*, timetable, worked_minutes, scheduled_minutes) -> int:
    """Excess over scheduled time when the timetable's overtime rule allows it."""
    try:
        overtime_rule = timetable.overtime_rule if timetable is not None else None
    except OvertimeRule.DoesNotExist:
        return 0
    if overtime_rule is None or not overtime_rule.enabled:
        return 0
    excess = worked_minutes - scheduled_minutes
    if excess < overtime_rule.minimum_minutes:
        return 0
    if overtime_rule.maximum_minutes is not None:
        return min(excess, overtime_rule.maximum_minutes)
    return excess


def _resolve_day_status(
    *,
    timetable,
    rule,
    summary,
    late_minutes,
    early_leave_minutes,
) -> str:
    """Derive the day's status from schedule, punches, and variances."""
    if timetable is not None and timetable.work_type == Timetable.WorkType.OFF:
        return DailyAttendance.Status.WORKED_HOLIDAY
    if timetable is not None and timetable.work_type == Timetable.WorkType.OVERTIME:
        return DailyAttendance.Status.OVERTIME
    require_in = timetable.require_check_in if timetable is not None else True
    require_out = timetable.require_check_out if timetable is not None else True
    if (require_in and not summary.has_check_in) or (
        require_out and not summary.has_check_out
    ):
        return DailyAttendance.Status.INCOMPLETE
    if (
        rule is not None
        and rule.late_to_absence_minutes
        and late_minutes >= rule.late_to_absence_minutes
    ):
        return DailyAttendance.Status.ABSENT
    if late_minutes > 0:
        return DailyAttendance.Status.LATE
    if early_leave_minutes > 0:
        return DailyAttendance.Status.EARLY_OUT
    return DailyAttendance.Status.PRESENT


def _day_variances(*, timetable, expected_in, expected_out, summary):
    """Return (late_minutes, early_leave_minutes) against expectations."""
    grace_in = timetable.late_in_grace_minutes if timetable is not None else 0
    grace_out = timetable.early_out_grace_minutes if timetable is not None else 0
    late_minutes = (
        max(0, minutes_between(expected_in, summary.first_in) - grace_in)
        if expected_in is not None and summary.first_in is not None
        else 0
    )
    early_leave_minutes = (
        max(0, minutes_between(summary.last_out, expected_out) - grace_out)
        if expected_out is not None and summary.last_out is not None
        else 0
    )
    return late_minutes, early_leave_minutes


def _store_daily_result(
    *,
    employee,
    day,
    shift,
    timetable,
    existing,
    summary,
    expected_in,
    expected_out,
    scheduled_minutes,
    late_minutes,
    early_leave_minutes,
    overtime_minutes,
    status,
) -> DailyAttendance:
    """Upsert the DailyAttendance row and rebuild its periods."""
    daily = existing if existing is not None else DailyAttendance(employee=employee, date=day)
    daily.calculation_version = (
        (existing.calculation_version or 0) + 1 if existing is not None else 1
    )
    daily.shift = shift
    daily.timetable = timetable
    daily.expected_in = expected_in
    daily.expected_out = expected_out
    daily.scheduled_minutes = scheduled_minutes
    daily.first_in = summary.first_in
    daily.last_out = summary.last_out
    daily.worked_minutes = summary.worked_minutes
    daily.break_minutes = summary.break_minutes
    daily.late_minutes = late_minutes
    daily.early_leave_minutes = early_leave_minutes
    daily.overtime_minutes = overtime_minutes
    daily.absent_minutes = (
        scheduled_minutes if status == DailyAttendance.Status.ABSENT else 0
    )
    daily.status = status
    daily.has_check_in = summary.has_check_in
    daily.has_check_out = summary.has_check_out
    daily.is_calculated = True
    daily.calculated_at = timezone.now()
    daily.full_clean()
    daily.save()

    AttendancePeriod.objects.filter(daily_attendance=daily).delete()
    AttendancePeriod.objects.bulk_create(
        AttendancePeriod(
            daily_attendance=daily,
            check_in=check_in,
            check_out=check_out,
            worked_minutes=(
                minutes_between(check_in.timestamp, check_out.timestamp)
                if check_in is not None and check_out is not None
                else 0
            ),
            is_valid=check_in is not None and check_out is not None,
        )
        for check_in, check_out in summary.pairs
    )
    return daily


def recalculate_daily_attendance(*, employee, day) -> DailyAttendance | None:
    """Recompute one employee-day from its punches (idempotent).

    Creates/updates the auto-calculated DailyAttendance and rebuilds
    its AttendancePeriods from IN -> OUT pairing. Manual records
    (``is_calculated=False``) are never touched. When no punches
    remain, an auto record is removed and None is returned.
    """
    shift, timetable = schedule_for_employee_on_date(employee=employee, day=day)

    existing = DailyAttendance.objects.filter(employee=employee, date=day).first()
    if existing is not None and not existing.is_calculated:
        return existing

    day_change = (
        timetable.day_change_time
        if timetable is not None
        else DEFAULT_DAY_CHANGE_TIME
    )
    window_start = timezone.make_aware(datetime.combine(day, day_change))
    window_end = window_start + timedelta(days=1)
    punches = list(
        AttendanceTransaction.objects.filter(
            employee=employee,
            timestamp__gte=window_start,
            timestamp__lt=window_end,
        ).order_by("timestamp", "id")
    )
    if not punches:
        if existing is not None:
            existing.delete()
        return None

    rule = AttendanceRule.objects.filter(is_active=True).order_by("id").first()
    duplicate_window = rule.duplicate_punch_window_minutes if rule is not None else 1
    allow_multiple = (
        timetable.multiple_in_out
        if timetable is not None
        else (rule.allow_multiple_in_out if rule is not None else False)
    )

    summary = summarize_pairs(
        pair_punches(
            dedupe_punches(punches, window_minutes=duplicate_window),
            allow_multiple_in_out=allow_multiple,
        )
    )
    expected_in, expected_out, scheduled_minutes = _expected_schedule(
        timetable=timetable, day=day
    )
    late_minutes, early_leave_minutes = _day_variances(
        timetable=timetable,
        expected_in=expected_in,
        expected_out=expected_out,
        summary=summary,
    )
    status = _resolve_day_status(
        timetable=timetable,
        rule=rule,
        summary=summary,
        late_minutes=late_minutes,
        early_leave_minutes=early_leave_minutes,
    )
    return _store_daily_result(
        employee=employee,
        day=day,
        shift=shift,
        timetable=timetable,
        existing=existing,
        summary=summary,
        expected_in=expected_in,
        expected_out=expected_out,
        scheduled_minutes=scheduled_minutes,
        late_minutes=late_minutes,
        early_leave_minutes=early_leave_minutes,
        overtime_minutes=_overtime_minutes(
            timetable=timetable,
            worked_minutes=summary.worked_minutes,
            scheduled_minutes=scheduled_minutes,
        ),
        status=status,
    )


def _employee_get_or_create_for_device(*, emp_code: str, branch=None) -> Employee:
    employee = employee_get_by_emp_code(emp_code=emp_code)
    if employee is not None:
        return employee

    return employee_create(
        first_name="Device",
        last_name=emp_code,
        emp_code=emp_code,
        branch=branch,
        # Punch-only record: no phone/password known; employee_create
        # generates a random password (invite link can set a known one).
        sync_to_device=False,
    )


def device_attendance_pull(
    *,
    serial_number: str,
    after_id: int | None = None,
    auto_create_employee: bool = True,
) -> dict:
    from companies.services import device_sync_state_update

    # Device is a SHARED_APPS model (lives in public schema). Always fetch it
    # in the public schema so the task works regardless of which schema the
    # Celery worker connection is currently set to (tenant_schemas_celery
    # switches schema per-task via headers and leaves the connection on the
    # last tenant otherwise).
    with schema_context(get_public_schema_name()):
        device = device_get_by_serial_number(serial_number=serial_number)
        if device is None:
            raise ValidationError({"serial_number": "Unknown device serial number."})
        if not device.is_active:
            raise ValidationError({"serial_number": "Device is inactive."})
        tenant_schema = device.company.schema_name
        if tenant_schema == get_public_schema_name():
            raise ValidationError(
                {"serial_number": "Device is assigned to the public schema; reassign it to a real company/tenant."}
            )
        # Capture branch/id while still in public schema; Branch is shared.
        device_branch_id = device.branch_id
        if after_id is None and device.last_gateway_log_id:
            after_id = device.last_gateway_log_id
        last_gateway_log_id = device.last_gateway_log_id

    try:
        logs = device_gateway_attendance_fetch(
            serial_number=serial_number,
            after_id=after_id,
        )
    except ValidationError as exc:
        with schema_context(get_public_schema_name()):
            device_sync_state_update(device=device, error=str(exc.message_dict))
        raise
    except Exception as exc:
        # Transient gateway errors (HTTPError 5xx, URLError, TimeoutError, OSError)
        # are now raised directly by the gateway to allow Celery retry.
        # Record the error on the device and re-raise the original exception
        # so the task's autoretry_for can handle it.
        from urllib.error import HTTPError, URLError

        if isinstance(exc, (HTTPError, URLError, TimeoutError, OSError)):
            with schema_context(get_public_schema_name()):
                device_sync_state_update(device=device, error=f"{type(exc).__name__}: {exc}")
            raise
        raise

    created = 0
    skipped = 0
    max_log_id = last_gateway_log_id
    # (employee pk, attendance day) -> employee, recalculated once per
    # day after the bulk insert instead of once per punch.
    affected_days: dict = {}

    with schema_context(tenant_schema):
        for log in logs:
            # Gateway identifies logs with ``gateway_log_id`` (older
            # payloads used ``id``); accept either.
            log_id = log.get("id")
            if log_id is None:
                log_id = log.get("gateway_log_id")
            if log_id is None:
                skipped += 1
                continue

            max_log_id = max(max_log_id, log_id)
            # Gateway sends ``user_id`` (device PIN); tolerate ``employee_id``.
            emp_code = log.get("user_id", log.get("employee_id"))
            if emp_code is None:
                skipped += 1
                continue
            emp_code = str(emp_code)
            timestamp_raw = log.get("timestamp")
            timestamp = parse_datetime(timestamp_raw) if timestamp_raw else None
            if timestamp is None:
                skipped += 1
                continue

            external_id = f"gateway:{log_id}"
            if AttendanceTransaction.objects.filter(external_id=external_id).exists():
                skipped += 1
                continue

            try:
                employee = employee_get_by_emp_code(emp_code=emp_code)
            except ValidationError:
                skipped += 1
                continue

            if employee is None:
                if not auto_create_employee:
                    skipped += 1
                    continue
                # Branch is a SHARED model (in public). Resolve it by id inside
                # the tenant context so the FK save works and we don't pass a
                # stale instance across schema_context boundaries.
                branch = None
                if device_branch_id is not None:
                    from companies.models import Branch

                    # Branch lives in public (shared), visible from tenant via search_path
                    branch = Branch.objects.filter(pk=device_branch_id).first()
                employee = _employee_get_or_create_for_device(
                    emp_code=emp_code,
                    branch=branch,
                )

            attendance_transaction_create(
                employee=employee,
                external_id=external_id,
                timestamp=timestamp,
                direction=direction_from_gateway_status(log.get("status")),
                source=AttendanceTransaction.Source.BIOMETRIC,
                external_employee_id=emp_code,
                raw_data=log,
                recalculate=False,
            )
            created += 1
            day, _, _ = resolve_punch_day(employee=employee, timestamp=timestamp)
            affected_days[(employee.pk, day)] = (employee, day)

    with schema_context(tenant_schema):
        for employee_pk, day in sorted(affected_days):
            employee, _ = affected_days[(employee_pk, day)]
            recalculate_daily_attendance(employee=employee, day=day)

    # Device state lives in public schema, so switch back before saving.
    with schema_context(get_public_schema_name()):
        device_sync_state_update(
            device=device,
            last_gateway_log_id=max_log_id,
            error="",
        )

    return {
        "serial_number": serial_number,
        "created": created,
        "skipped": skipped,
        "last_log_id": max_log_id,
    }
