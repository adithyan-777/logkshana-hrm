"""django-q2 tasks for per-employee attendance calculation.

Chain: nightly fanout (public schema) -> one enqueue task per tenant ->
one calc task per employee. Every task carries its tenant
``schema_name`` explicitly and switches schema itself, so tasks are
safe no matter which schema the worker connection is left on.

Enqueue with ``django_q.tasks.async_task`` by string path, e.g.
``async_task("attendance.q2_tasks.enqueue_tenant_day", ...)``.
"""

from datetime import date

from django.utils import timezone

GROUP_LABEL = "attendance-calc"


def _day_from_iso(day_iso: str | None) -> date:
    if day_iso:
        return date.fromisoformat(day_iso)
    return timezone.localdate()


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
            Employee.objects.filter(is_active=True).values_list(
                "id", flat=True
            )
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
