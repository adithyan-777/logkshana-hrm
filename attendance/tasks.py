from urllib.error import HTTPError, URLError

from django.core.exceptions import ValidationError
from django_tenants.utils import get_public_schema_name, schema_context

from config.celery import app


@app.task
def device_attendance_sync_all_task() -> None:
    from companies.models import Device

    # Device is SHARED (public schema). Query must be in public schema,
    # otherwise a worker whose connection is still on a previous tenant
    # (tenant_schemas_celery leaves the connection on the last tenant)
    # will see an empty result.
    with schema_context(get_public_schema_name()):
        devices = list(
            Device.objects.filter(is_active=True)
            .select_related("company")
            .values_list("serial_number", "company__schema_name")
        )

    for serial_number, schema_name in devices:
        # Use schema_context so tenant_schemas_celery's headers_with_schema
        # captures the tenant's schema in the message headers. The worker's
        # prerun handler (switch_schema) will then set the connection to that
        # tenant before the subtask runs.
        with schema_context(schema_name):
            device_attendance_sync_task.delay(serial_number)


@app.task(
    bind=True,
    autoretry_for=(HTTPError, URLError, TimeoutError, OSError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def device_attendance_sync_task(
    self, serial_number: str, schema_name: str | None = None
) -> dict:
    from attendance.services import device_attendance_pull

    # schema_name is optional for backwards compatibility (existing callers
    # pass only serial_number). The service itself is now robust: it fetches
    # Device in the public schema and writes attendance in the tenant schema.
    # If a schema_name is explicitly passed, honour it by switching to that
    # tenant before calling the service (covers the case where the caller
    # already knows the tenant and the worker's auto-switch via headers is
    # available as well).
    def _call():
        if schema_name:
            with schema_context(schema_name):
                return device_attendance_pull(serial_number=serial_number)
        return device_attendance_pull(serial_number=serial_number)

    try:
        return _call()
    except ValidationError as exc:
        # Retry transient gateway ValidationErrors (e.g. 502 Bad Gateway when
        # gateway still wraps 5xx as ValidationError in older mocks or 4xx vs 5xx
        # confusion). Permanent errors like "Unknown device" should NOT retry.
        msg_dict = getattr(exc, "message_dict", {}) or {}
        gateway_msgs = msg_dict.get("device_gateway", [])
        # Gateway messages can be list or string
        joined = (
            " ".join(gateway_msgs)
            if isinstance(gateway_msgs, list)
            else str(gateway_msgs)
        )
        # Also check str(exc) for backwards compat with tests mocking plain ValidationError
        check_str = joined or str(exc)
        is_transient = any(
            code in check_str
            for code in (
                "502",
                "503",
                "504",
                "500",
                "Gateway unreachable",
                "unreachable",
                "timeout",
                "timed out",
            )
        )
        # Only retry if it's a gateway transient error and we have retries left
        if is_transient and "device_gateway" in msg_dict:
            # Use Celery's retry mechanism (respects max_retries/backoff)
            raise self.retry(exc=exc)
        raise
