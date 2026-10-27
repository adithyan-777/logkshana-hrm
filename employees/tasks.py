"""Dramatiq actors for device user enrollment.

Enqueued from the request path (``employees.services``) via
``transaction.on_commit`` + ``actor.send`` so web responses never block
on the device gateway. Every actor carries its tenant ``schema_name``
explicitly and switches schema itself.

Retry model: transient gateway failures are re-raised so dramatiq's
``Retries`` middleware retries them with capped exponential backoff;
permanent failures (no emp_code, unknown/inactive device, 4xx) are
logged + reported to Sentry and never retried.
"""

import logging

import dramatiq

logger = logging.getLogger(__name__)

#: Per-task time limit (ms) for a single device push.
DEVICE_USER_TIME_LIMIT_MS = 120_000
#: Retry bounds for transient gateway failures (ms).
DEVICE_USER_MIN_BACKOFF_MS = 60_000
DEVICE_USER_MAX_BACKOFF_MS = 600_000
#: Bounded retries per push.
DEVICE_USER_MAX_RETRIES = 3


@dramatiq.actor(
    max_retries=DEVICE_USER_MAX_RETRIES,
    min_backoff=DEVICE_USER_MIN_BACKOFF_MS,
    max_backoff=DEVICE_USER_MAX_BACKOFF_MS,
    time_limit=DEVICE_USER_TIME_LIMIT_MS,
)
def create_device_user(schema_name: str, employee_id: int, serial_number: str):
    """Push one employee to one device.

    Permanent failures (no emp_code, unknown/inactive device, 4xx)
    return without retry; transient gateway failures raise and are
    retried by dramatiq.
    """
    from django_tenants.utils import schema_context

    from attendance.integrations.gateway import is_transient_gateway_error
    from employees.models import Employee
    from employees.services import device_user_create

    try:
        with schema_context(schema_name):
            employee = Employee.objects.get(pk=employee_id)
            device_user_create(employee=employee, serial_number=serial_number)
    except Exception as exc:
        if is_transient_gateway_error(exc, field_keys=("device", "device_gateway")):
            raise
        logger.error(
            "Permanent device-user push failure (schema=%s, employee=%s, "
            "serial=%s): %s",
            schema_name,
            employee_id,
            serial_number,
            exc,
        )
        return {
            "schema": schema_name,
            "employee_id": employee_id,
            "serial_number": serial_number,
            "pushed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "schema": schema_name,
        "employee_id": employee_id,
        "serial_number": serial_number,
        "pushed": True,
    }


@dramatiq.actor(
    max_retries=DEVICE_USER_MAX_RETRIES,
    min_backoff=DEVICE_USER_MIN_BACKOFF_MS,
    max_backoff=DEVICE_USER_MAX_BACKOFF_MS,
    time_limit=DEVICE_USER_TIME_LIMIT_MS,
)
def delete_device_user(schema_name: str, emp_code: str, serial_number: str):
    """Remove one device user (PIN).

    Takes the PIN, not an employee id: the employee row is already gone
    when this runs (enqueued on_commit from ``employee_delete``).
    Permanent failures return without retry; transient gateway failures
    raise and are retried by dramatiq.
    """
    from attendance.integrations.gateway import is_transient_gateway_error
    from employees.services import device_user_delete

    try:
        device_user_delete(emp_code=emp_code, serial_number=serial_number)
    except Exception as exc:
        if is_transient_gateway_error(exc, field_keys=("device", "device_gateway")):
            raise
        logger.error(
            "Permanent device-user delete failure (schema=%s, emp_code=%s, "
            "serial=%s): %s",
            schema_name,
            emp_code,
            serial_number,
            exc,
        )
        return {
            "schema": schema_name,
            "emp_code": emp_code,
            "serial_number": serial_number,
            "deleted": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "schema": schema_name,
        "emp_code": emp_code,
        "serial_number": serial_number,
        "deleted": True,
    }
