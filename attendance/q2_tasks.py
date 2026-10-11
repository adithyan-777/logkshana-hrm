"""django-q2 tasks for per-employee attendance calculation.

Chain: nightly fanout (public schema) -> one enqueue task per tenant ->
one calc task per employee. Every task carries its tenant
``schema_name`` explicitly and switches schema itself, so tasks are
safe no matter which schema the worker connection is left on.

Enqueue with ``django_q.tasks.async_task`` by string path, e.g.
``async_task("attendance.q2_tasks.enqueue_tenant_day", ...)``.
"""

from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from django_q.models import Schedule
from django_q.tasks import async_task, schedule
from django_tenants.utils import get_tenant_model, schema_context

P = "attendance.q2_tasks"

GROUP_LABEL = "attendance-calc"

#: Task group for device-gateway sync tasks (q2 admin filtering).
DEVICE_SYNC_GROUP = "device-sync"
#: Bounded retries per device pull (Celery max_retries=3 equivalent).
DEVICE_SYNC_MAX_RETRIES = 3
#: Per-task timeout (s) for a single device pull; cluster default is lower.
DEVICE_SYNC_TIMEOUT = 300
#: Base backoff between retries; delay is base * 2**attempt.
DEVICE_SYNC_RETRY_BASE_SECONDS = 60

#: How far ahead of now a shift may start and still be materialized.
LEAD = timedelta(hours=2)
#: Grace after shift start before the absent-check fires.
GRACE = timedelta(minutes=30)


def _day_from_iso(day_iso: str | None) -> date:
    if day_iso:
        return date.fromisoformat(day_iso)
    return timezone.localdate()


def materialize_shifts_all_tenants():
    for t in get_tenant_model().objects.exclude(schema_name="public"):
        async_task(f"{P}.materialize_shifts_for_tenant", t.schema_name)


def materialize_shifts_for_tenant(schema_name):
    """Create ``ScheduledShiftDay`` rows for today + tomorrow.

    Every assigned/overridden employee gets a plan row; shifts starting
    beyond the lead horizon are left for a later run. Day-off and holiday
    rows are always materialized. Existing rows are never touched.
    """
    from django.db.models import Q

    from employees.models import Employee
    from schedule.models import (
        EmployeeScheduleAssignment,
        EmployeeScheduleOverride,
        ScheduledShiftDay,
    )
    from schedule.services import get_or_materialize_shift

    with schema_context(schema_name):
        now = timezone.now()
        horizon = now + LEAD
        today = timezone.localdate(now)

        for day in (today, today + timedelta(days=1)):
            candidates = set(
                EmployeeScheduleOverride.objects.filter(date=day).values_list(
                    "employee_id", flat=True
                )
            )
            candidates |= set(
                EmployeeScheduleAssignment.objects.filter(
                    is_active=True,
                    start_date__lte=day,
                    schedule__is_active=True,
                )
                .filter(Q(end_date__gte=day) | Q(end_date__isnull=True))
                .values_list("employees__pk", flat=True)
            )
            candidates.discard(None)
            employees = Employee.objects.filter(
                pk__in=candidates, is_active=True
            ).order_by("pk")
            for employee in employees.iterator():
                shift, created = get_or_materialize_shift(employee=employee, day=day)
                if shift is None or not created:
                    continue
                if (
                    shift.day_type != ScheduledShiftDay.DayType.WORKING
                    or shift.shift_start is None
                ):
                    continue
                if shift.shift_start > horizon or shift.shift_end <= now:
                    continue
                if shift.attendance_activities.exists():
                    continue
                transaction.on_commit(
                    lambda pk=shift.pk, s=shift.shift_start: after_shift_created(
                        pk, s, schema_name
                    )
                )


def after_shift_created(shift_pk, start_at, schema_name):
    async_task(f"{P}.notify_employee_shift_upcoming", shift_pk, schema_name)
    schedule(
        f"{P}.mark_absent_if_no_punch",
        shift_pk,
        schema_name,
        name=f"absent-check:{schema_name}:{shift_pk}",
        schedule_type=Schedule.ONCE,
        next_run=start_at + GRACE,
        repeats=1,
    )


def notify_employee_shift_upcoming(shift_pk, schema_name):
    with schema_context(schema_name):
        pass


def mark_absent_if_no_punch(shift_pk, schema_name):
    with schema_context(schema_name):
        pass


def fanout_daily_attendance(day_iso: str | None = None) -> dict:
    """Public-schema entry point: fan out to one task per tenant.

    Runs from the nightly q2 Schedule. Returns {"tenants": N}.
    """
    from django_q.tasks import async_task

    from companies.models import Company

    day_iso = day_iso or timezone.localdate().isoformat()
    schemas = list(
        Company.objects.exclude(schema_name="public").values_list(
            "schema_name", flat=True
        )
    )
    for schema_name in schemas:
        async_task(
            "attendance.q2_tasks.enqueue_tenant_day",
            schema_name,
            day_iso,
            group=GROUP_LABEL,
        )
    return {"tenants": len(schemas)}


def enqueue_tenant_day(schema_name: str, day_iso: str | None = None) -> dict:
    """Enqueue one calc task per active employee of a tenant."""
    from django_q.tasks import async_task
    from django_tenants.utils import schema_context

    from employees.models import Employee

    day_iso = day_iso or timezone.localdate().isoformat()
    with schema_context(schema_name):
        employee_ids = list(
            Employee.objects.filter(is_active=True).values_list("id", flat=True)
        )
    for employee_id in employee_ids:
        async_task(
            "attendance.q2_tasks.calculate_employee_day",
            schema_name,
            employee_id,
            day_iso,
            group=GROUP_LABEL,
        )
    return {"schema": schema_name, "employees": len(employee_ids)}


def calculate_employee_day(
    schema_name: str, employee_id: int, day_iso: str | None = None
) -> dict:
    """Calculate and store one employee's attendance for one day."""
    from django_tenants.utils import schema_context

    from attendance.recalculation import recalculate_attendance
    from employees.models import Employee

    day = _day_from_iso(day_iso)
    with schema_context(schema_name):
        employee = Employee.objects.get(id=employee_id)
        row = recalculate_attendance(employee=employee, day=day)
    if row is None:
        return {
            "schema": schema_name,
            "employee_id": employee_id,
            "day": day.isoformat(),
            "recorded": False,
        }
    return {
        "schema": schema_name,
        "employee_id": employee_id,
        "day": day.isoformat(),
        "recorded": True,
        "attendance_id": row.id,
        "status": row.status,
    }


def fanout_device_sync() -> dict:
    """q2 entry point (5-minute Schedule): fan out to one task per device.

    Runs from the ``device-attendance-sync`` q2 Schedule.
    ``device_attendance_pull`` is schema-robust (public-schema Device
    fetch, tenant-schema writes), so per-device tasks need no schema_name.
    """
    from django_q.tasks import async_task
    from django_tenants.utils import get_public_schema_name, schema_context

    from companies.models import Device

    with schema_context(get_public_schema_name()):
        serials = list(
            Device.objects.filter(is_active=True).values_list(
                "serial_number", flat=True
            )
        )
    for serial_number in serials:
        async_task(
            "attendance.q2_tasks.sync_device_attendance",
            serial_number,
            group=DEVICE_SYNC_GROUP,
            timeout=DEVICE_SYNC_TIMEOUT,
        )
    return {"devices": len(serials)}


def sync_device_attendance(serial_number: str, attempt: int = 0) -> dict:
    """Pull attendance logs for one device; bounded retry on transient errors.

    Permanent failures (unknown/inactive device, 4xx) raise immediately.
    Transient gateway failures (5xx, unreachable, timeouts) are re-queued
    as a one-off q2 Schedule with exponential backoff, up to
    ``DEVICE_SYNC_MAX_RETRIES`` retries.
    """
    from django_q.models import Schedule
    from django_q.tasks import schedule as schedule_once
    from django_tenants.utils import get_public_schema_name, schema_context

    from attendance.integrations.gateway import is_transient_gateway_error
    from attendance.services import device_attendance_pull

    try:
        return device_attendance_pull(serial_number=serial_number)
    except Exception as exc:
        if attempt < DEVICE_SYNC_MAX_RETRIES and is_transient_gateway_error(exc):
            delay = DEVICE_SYNC_RETRY_BASE_SECONDS * (2**attempt)
            with schema_context(get_public_schema_name()):
                schedule_once(
                    "attendance.q2_tasks.sync_device_attendance",
                    serial_number,
                    attempt + 1,
                    schedule_type=Schedule.ONCE,
                    next_run=timezone.now() + timedelta(seconds=delay),
                )
            return {
                "serial_number": serial_number,
                "retried": True,
                "attempt": attempt + 1,
            }
        raise
