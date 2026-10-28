from datetime import date, datetime, time, timedelta
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery, Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.calculation import direction_from_gateway_status_label
from attendance.integrations.gateway import device_gateway_attendance_fetch
from attendance.models import (
    Attendance,
    AttendanceActivity,
    WorkSession,
)
from companies.selectors import device_get_by_serial_number
from employees.models import Employee
from employees.selectors import employee_get_by_emp_code
from employees.services import employee_create
from policies.selectors import attendance_policy_is_unscheduled


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
    # Punch-based Attendance calculation only runs when the tenant
    # policy is "unscheduled". In "scheduled" mode the punch is just
    # recorded; Attendance rows come from the (schedule-driven)
    # calculation instead.
    if attendance_policy_is_unscheduled():
        attendance_update_for_punch(
            employee=activity.employee,
            punch_time=activity.punch_time,
            direction=activity.direction,
            activity=activity,
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


# -- Auto-ABSENT midnight job -------------------------------------------


def employees_absent_condition(*, day: date):
    """Employees eligible for an auto-ABSENT row on ``day``.

    Single pluggable rule for the midnight job. An employee is
    eligible when they are active, hold no Attendance row for the
    day, have no punches already recorded that day, and were punched
    OUT before the day started (their last punch is a check-out — or
    they never punched at all).

    An employee whose last punch is a check-in might still be in the
    building (overnight shift, missed check-out), so they are skipped.
    Tweak the query here to change who gets marked absent (branch,
    employee_type, schedule coverage, ...).
    """
    day_start = timezone.make_aware(datetime.combine(day, time.min))
    last_direction = AttendanceActivity.objects.filter(
        employee=OuterRef("pk"),
        punch_time__lt=day_start,
    ).order_by("-punch_time", "-id").values("direction")[:1]
    return (
        Employee.objects.filter(is_active=True)
        .exclude(
            attendances__day=day,
        )
        .exclude(
            attendance_activities__punch_time__gte=day_start,
            attendance_activities__punch_time__lt=day_start + timedelta(days=1),
        )
        .annotate(last_direction=Subquery(last_direction))
        .filter(
            Q(last_direction=AttendanceActivity.Direction.OUT)
            | Q(last_direction__isnull=True)
        )
    )


@transaction.atomic
def attendance_absent_rows_ensure(*, day: date) -> list[Attendance]:
    """Create auto-ABSENT Attendance rows for every eligible employee.

    Idempotent: employees already holding a row for ``day`` are
    excluded by the condition, and ``get_or_create`` absorbs races.
    Rows are written with ``is_calculated=False`` (machine-generated
    today, but treated like hand-made rows — the future daily
    calculation never overwrites them).
    """
    created = []
    for employee in employees_absent_condition(day=day).iterator():
        row, was_created = Attendance.objects.get_or_create(
            employee=employee,
            day=day,
            defaults={
                "status": Attendance.Status.ABSENT,
                "is_calculated": False,
            },
        )
        if was_created:
            created.append(row)
    return created
# -- Punch -> WorkSession pairing ----------------------------------------


def _attendance_row_ensure(*, employee, day) -> Attendance:
    row, _ = Attendance.objects.get_or_create(
        employee=employee,
        day=day,
        defaults={
            "status": Attendance.Status.ABSENT,
            "is_calculated": False,
        },
    )
    return row


def _open_work_session_get(*, employee) -> WorkSession | None:
    """The employee's most recent open (unclosed) work session.

    Only one open session can exist at a time; ordering covers the
    overnight case, where the open session belongs to an earlier day.
    """
    return (
        WorkSession.objects.filter(
            employee=employee,
            check_out__isnull=True,
        )
        .order_by("-day", "-check_in")
        .first()
    )


def _activity_attendance_link(activity, attendance):
    """Link a consumed punch to the day row it was processed into.

    Powers the punch-log view (``is_attendance_processed``); punch
    rows ingested without an activity (direct primitive calls, tests)
    skip the link.
    """
    if activity is not None and activity.attendance_id is None:
        activity.attendance = attendance
        activity.save(update_fields=["attendance", "updated_at"])


@transaction.atomic
def attendance_update_for_punch(
    *,
    employee,
    punch_time,
    direction: str,
    activity: AttendanceActivity | None = None,
) -> Attendance | None:
    """Apply one punch to the employee's attendance via work sessions.

    An IN punch opens a ``WorkSession`` under the punch day's daily
    row (created on demand) unless one is already open — a second IN
    while a session is still open is ignored. The daily ``check_in``
    stamps only the day's first session.

    An OUT punch closes the most recent open session — today first,
    then an earlier day's (overnight shift) — records ``total_time``
    on the session, moves the daily ``check_out`` to that session's
    out time, and refreshes ``total_work_time`` as the sum of the
    closed sessions. An OUT with no open session and an OUT earlier
    than the open session's ``check_in`` stay punch-log-only and
    touch no rows.

    Punches with an unknown direction (devices sending no status
    label) leave rows untouched.
    """
    if direction == AttendanceActivity.Direction.IN:
        open_session = _open_work_session_get(employee=employee)
        if open_session is not None:
            _activity_attendance_link(activity, open_session.attendance)
            return open_session.attendance
        day = timezone.localtime(punch_time).date()
        row = _attendance_row_ensure(employee=employee, day=day)
        WorkSession.objects.create(
            employee=employee,
            attendance=row,
            day=day,
            in_punch=activity,
            check_in=punch_time,
        )
        if row.check_in is None:
            row.check_in = punch_time
            if row.status in (
                Attendance.Status.ABSENT,
                Attendance.Status.INCOMPLETE,
            ):
                row.status = Attendance.Status.PRESENT
        row.save(update_fields=["check_in", "status", "updated_at"])
        _activity_attendance_link(activity, row)
        return row
    if direction == AttendanceActivity.Direction.OUT:
        session = _open_work_session_get(employee=employee)
        if session is None:
            # Stray OUT: record it in the punch log only; daily rows
            # are not created or stamped for unpaired check-outs.
            return None
        if punch_time <= session.check_in:
            # Stale or replayed punch — never pair backwards in time.
            return None
        session.out_punch = activity
        session.check_out = punch_time
        session.total_time = punch_time - session.check_in
        session.save(
            update_fields=["out_punch", "check_out", "total_time", "updated_at"]
        )
        row = session.attendance
        row.check_out = session.check_out
        row.total_work_time = (
            WorkSession.objects.filter(
                attendance=row,
                check_out__isnull=False,
            )
            .aggregate(total=Sum("total_time"))["total"]
            or timedelta(0)
        )
        row.save(update_fields=["check_out", "total_work_time", "updated_at"])
        _activity_attendance_link(activity, row)
        return row
    return None

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
