from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.calculation import direction_from_gateway_status_label
from attendance.integrations.gateway import device_gateway_attendance_fetch
from attendance.models import Attendance, AttendanceActivity
from companies.selectors import device_get_by_serial_number
from employees.models import Employee
from employees.selectors import employee_get_by_emp_code
from employees.services import employee_create


@transaction.atomic
def activity_create(
    *,
    employee,
    punch_time,
    direction: str = AttendanceActivity.Direction.UNKNOWN,
    method: str = AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
    external_id: str | None = None,
    raw_data=None,
) -> AttendanceActivity:
    if not external_id:
        external_id = f"manual:{uuid4().hex}"
    else:
        existing = AttendanceActivity.objects.filter(external_id=external_id).first()
        if existing is not None:
            return existing
    activity = AttendanceActivity(
        employee=employee,
        punch_time=punch_time,
        direction=direction,
        method=method,
        external_id=external_id,
        raw_data=raw_data or {},
    )
    activity.full_clean()
    activity.save()
    return activity


@transaction.atomic
def activity_update(
    *,
    activity: AttendanceActivity,
    employee,
    punch_time,
    direction: str,
    method: str,
    external_id: str | None = None,
    raw_data=None,
) -> AttendanceActivity:
    activity.employee = employee
    # external_id is a stable record identifier: keep the existing one
    # unless an explicit replacement is given.
    if external_id:
        activity.external_id = external_id
    activity.punch_time = punch_time
    activity.direction = direction
    activity.method = method
    activity.raw_data = raw_data or {}
    activity.full_clean()
    activity.save()
    return activity


@transaction.atomic
def activity_delete(*, activity: AttendanceActivity) -> AttendanceActivity:
    """Deletes the punch."""
    activity.delete()
    return activity


@transaction.atomic
def attendance_record_create(
    *,
    employee,
    day,
    status: str,
    shift=None,
) -> Attendance:
    """Create a hand-made attendance row (never auto-overwritten)."""
    row = Attendance(
        employee=employee,
        day=day,
        status=status,
        shift=shift,
        is_calculated=False,
    )
    row.full_clean()
    row.save()
    return row


@transaction.atomic
def attendance_record_update(
    *,
    attendance: Attendance,
    employee,
    day,
    status: str,
    shift=None,
) -> Attendance:
    attendance.employee = employee
    attendance.day = day
    attendance.status = status
    attendance.shift = shift
    attendance.is_calculated = False
    attendance.full_clean()
    attendance.save()
    return attendance


@transaction.atomic
def attendance_record_delete(*, attendance: Attendance) -> Attendance:
    """Deletes a hand-made attendance record.

    Calculated rows are written by the daily calculation: they are
    removed by dropping the punches, never by hand.
    """
    if attendance.is_calculated:
        raise ValidationError(
            "Calculated attendance cannot be deleted; remove the punch or "
            "the schedule entry instead."
        )
    attendance.delete()
    return attendance


# Short aliases matching the "<entity>_<action>" naming used by URLs/views.
record_update = attendance_record_update
record_delete = attendance_record_delete


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
    # worker connection is currently set to.
    with schema_context(get_public_schema_name()):
        device = device_get_by_serial_number(serial_number=serial_number)
        if device is None:
            raise ValidationError({"serial_number": "Unknown device serial number."})
        if not device.is_active:
            raise ValidationError({"serial_number": "Device is inactive."})
        tenant_schema = device.company.schema_name
        if tenant_schema == get_public_schema_name():
            raise ValidationError(
                {
                    "serial_number": "Device is assigned to the public schema; reassign it to a real company/tenant."
                }
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
        # Transient gateway errors (HTTPError 5xx, URLError, TimeoutError,
        # OSError) are raised directly by the gateway to allow task-layer retry.
        from urllib.error import HTTPError, URLError

        if isinstance(exc, (HTTPError, URLError, TimeoutError, OSError)):
            with schema_context(get_public_schema_name()):
                device_sync_state_update(
                    device=device, error=f"{type(exc).__name__}: {exc}"
                )
            raise
        raise

    created = 0
    skipped = 0
    max_log_id = last_gateway_log_id

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
            # Gateway payloads may stringify the id; the cursor handed back
            # to the next fetch is an integer.
            try:
                log_id = int(log_id)
            except (TypeError, ValueError):
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
            if AttendanceActivity.objects.filter(external_id=external_id).exists():
                skipped += 1
                continue

            try:
                employee = employee_get_by_emp_code(emp_code=emp_code)
            except ValidationError:
                skipped += 1
                continue

            if employee is None:
                # ``employee_get_by_emp_code`` only sees active records, so an
                # existing-but-deactivated code would otherwise be treated as
                # unknown and auto-created a second time.
                if Employee.objects.filter(emp_code=emp_code).exists():
                    skipped += 1
                    continue
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

            activity_create(
                employee=employee,
                punch_time=timestamp,
                direction=direction_from_gateway_status_label(log.get("status_label")),
                method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
                external_id=external_id,
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
