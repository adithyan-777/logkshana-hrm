"""django-q2 tasks for device user enrollment.

Enqueued from the request path (``employees.services``) via
``transaction.on_commit`` + ``async_task`` so web responses never block
on the device gateway. Every task carries its tenant ``schema_name``
explicitly and switches schema itself.
"""

from datetime import timedelta

from django.utils import timezone

#: Task group for device-user push tasks (q2 admin filtering).
DEVICE_USER_GROUP = "device-user"
#: Bounded retries per push (Celery max_retries=3 equivalent).
DEVICE_USER_MAX_RETRIES = 3
#: Per-task timeout (s) for a single device push.
DEVICE_USER_TIMEOUT = 120
#: Base backoff between retries; delay is base * 2**attempt.
DEVICE_USER_RETRY_BASE_SECONDS = 60


def create_device_user(
    schema_name: str, employee_id: int, serial_number: str, attempt: int = 0
) -> dict:
    """Push one employee to one device; bounded retry on transient errors.

    Permanent failures (no emp_code, unknown/inactive device, 4xx) raise
    immediately. Transient gateway failures are re-queued as a one-off q2
    Schedule with exponential backoff, up to ``DEVICE_USER_MAX_RETRIES``.
    """
    from django_q.models import Schedule
    from django_q.tasks import schedule as schedule_once
    from django_tenants.utils import get_public_schema_name, schema_context

    from attendance.integrations.gateway import is_transient_gateway_error
    from employees.models import Employee
    from employees.services import device_user_create

    try:
        with schema_context(schema_name):
            employee = Employee.objects.get(pk=employee_id)
            device_user_create(employee=employee, serial_number=serial_number)
    except Exception as exc:
        if attempt < DEVICE_USER_MAX_RETRIES and is_transient_gateway_error(
            exc, field_keys=("device", "device_gateway")
        ):
            delay = DEVICE_USER_RETRY_BASE_SECONDS * (2**attempt)
            with schema_context(get_public_schema_name()):
                schedule_once(
                    "employees.q2_tasks.create_device_user",
                    schema_name,
                    employee_id,
                    serial_number,
                    attempt + 1,
                    schedule_type=Schedule.ONCE,
                    next_run=timezone.now() + timedelta(seconds=delay),
                )
            return {
                "schema": schema_name,
                "employee_id": employee_id,
                "serial_number": serial_number,
                "retried": True,
                "attempt": attempt + 1,
            }
        raise
    return {
        "schema": schema_name,
        "employee_id": employee_id,
        "serial_number": serial_number,
        "pushed": True,
    }
