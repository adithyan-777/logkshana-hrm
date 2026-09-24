from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.calculation import (
    attendance_day_for_punch,
    direction_from_gateway_status,
)
from attendance.integrations.gateway import device_gateway_attendance_fetch
from attendance.models import Attendance, AttendanceActivity
from attendance.recalculation import (
    DEFAULT_DAY_CHANGE_TIME,
    recalculate_attendance,
)
from companies.selectors import device_get_by_serial_number
from employees.models import Employee
from employees.selectors import employee_get_by_emp_code
from employees.services import employee_create
from schedule.selectors import resolve_schedule_for_employee_on_date


def resolve_punch_day(*, employee, timestamp):
    """Return the (day, schedule, timetable) a punch belongs to.

    Early-morning punches fall on the previous attendance day per the
    timetable's ``day_change_time`` (08:00 when unscheduled), so an
    overnight check-out lands on the day the shift started.
    """
    ts = timestamp
    if timezone.is_naive(ts):
        ts = timezone.make_aware(ts)
    local_date = timezone.localtime(ts).date()
    resolved = resolve_schedule_for_employee_on_date(
        employee=employee, day=local_date
    )
    timetable = resolved.timetable
    day_change = (
        timetable.day_change_time
        if timetable is not None
        else DEFAULT_DAY_CHANGE_TIME
    )
    day = attendance_day_for_punch(timestamp=ts, day_change_time=day_change)
    if day != local_date:
        prev = resolve_schedule_for_employee_on_date(employee=employee, day=day)
        if prev.timetable is not None:
            resolved, timetable = prev, prev.timetable
    return day, resolved.schedule, timetable


def recalculate_attendance_for_punch(*, employee, timestamp):
    """Recompute the attendance day a single punch belongs to."""
    day, _, _ = resolve_punch_day(employee=employee, timestamp=timestamp)
    return recalculate_attendance(employee=employee, day=day)


@transaction.atomic
def activity_create(
    *,
    employee,
    punch_time,
    direction: str = AttendanceActivity.Direction.UNKNOWN,
    method: str = AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
    external_id: str | None = None,
    raw_data=None,
    recalculate: bool = True,
) -> AttendanceActivity:
    if not external_id:
        external_id = f"manual:{uuid4().hex}"
    else:
        existing = AttendanceActivity.objects.filter(
            external_id=external_id
        ).first()
        if existing is not None:
            return existing
    activity = AttendanceActivity(
        employee=employee,
        punch_time=punch_time,
        direction=direction,
        method=method,
        external_id=external_id,
        raw_data=raw_data or {},
        # Hand-entered punches arrive already human-handled.
        is_attendance_processed=(
            method == AttendanceActivity.AttendanceActivityMethodType.MANUAL
        ),
    )
    activity.full_clean()
    activity.save()
    if recalculate:
        recalculate_attendance_for_punch(
            employee=activity.employee,
            timestamp=activity.punch_time,
        )
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
    recalculate: bool = True,
) -> AttendanceActivity:
    old_employee = activity.employee
    old_punch_time = activity.punch_time
    activity.employee = employee
    # external_id is a stable record identifier: keep the existing one
    # unless an explicit replacement is given.
    if external_id:
        activity.external_id = external_id
    activity.punch_time = punch_time
    activity.direction = direction
    activity.method = method
    activity.raw_data = raw_data or {}
    if method == AttendanceActivity.AttendanceActivityMethodType.MANUAL:
        # A manual correction counts as human-handled; never auto-cleared.
        activity.is_attendance_processed = True
    activity.full_clean()
    activity.save()
    if recalculate:
        recalculate_attendance_for_punch(
            employee=activity.employee,
            timestamp=activity.punch_time,
        )
        if (
            old_employee.pk != activity.employee.pk
            or old_punch_time != activity.punch_time
        ):
            recalculate_attendance_for_punch(
                employee=old_employee,
                timestamp=old_punch_time,
            )
    return activity


@transaction.atomic
def activity_delete(
    *, activity: AttendanceActivity, recalculate: bool = True
) -> AttendanceActivity:
    """Soft-deletes the punch (recoverable via all_objects)."""
    employee = activity.employee
    punch_time = activity.punch_time
    activity.delete()
    if recalculate:
        recalculate_attendance_for_punch(
            employee=employee,
            timestamp=punch_time,
        )
    return activity


@transaction.atomic
def attendance_record_create(
    *,
    employee,
    day,
    status: str,
    shift=None,
    force: bool = False,
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
    if force:
        return recalculate_attendance(employee=employee, day=day, force=True)
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
    """Soft-deletes the record (recoverable via all_objects)."""
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
        # OSError) are raised directly by the gateway to allow Celery retry.
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
    # (employee pk, attendance day) -> (employee, day), recalculated once per
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
            if AttendanceActivity.objects.filter(
                external_id=external_id
            ).exists():
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

            activity_create(
                employee=employee,
                punch_time=timestamp,
                direction=direction_from_gateway_status(log.get("status")),
                method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
                external_id=external_id,
                raw_data=log,
                recalculate=False,
            )
            created += 1
            day, _, _ = resolve_punch_day(employee=employee, timestamp=timestamp)
            affected_days[(employee.pk, day)] = (employee, day)

    with schema_context(tenant_schema):
        for employee_pk, day in sorted(affected_days):
            employee, _ = affected_days[(employee_pk, day)]
            recalculate_attendance(employee=employee, day=day)

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
