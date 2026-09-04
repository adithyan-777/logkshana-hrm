from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.integrations.gateway import device_gateway_attendance_fetch
from attendance.models import (
    AttendanceCorrection,
    AttendanceRule,
    AttendanceTransaction,
    DailyAttendance,
)
from companies.selectors import device_get_by_serial_number
from employees.models import Employee
from employees.selectors import employee_get_by_emp_code
from employees.services import employee_create


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
    if (
        correction.check_in
        and correction.check_out
        and correction.check_out < correction.check_in
    ):
        raise ValidationError("Check-out must be on or after check-in.")


def _employee_get_or_create_for_device(*, emp_code: str, branch=None) -> Employee:
    employee = employee_get_by_emp_code(emp_code=emp_code)
    if employee is not None:
        return employee

    return employee_create(
        first_name="Device",
        last_name=emp_code,
        emp_code=emp_code,
        branch=branch,
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

    with schema_context(tenant_schema):
        for log in logs:
            log_id = log.get("id")
            if log_id is None:
                skipped += 1
                continue

            max_log_id = max(max_log_id, log_id)
            emp_code = str(log["user_id"])
            timestamp = parse_datetime(log["timestamp"])
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
                direction=AttendanceTransaction.Direction.UNKNOWN,
                source=AttendanceTransaction.Source.BIOMETRIC,
                external_employee_id=emp_code,
                raw_data=log,
            )
            created += 1

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
