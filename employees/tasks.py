import time
from urllib.error import HTTPError, URLError

from django.core.exceptions import ValidationError
from django.db import connection

from config.celery import app
from employees.models import Employee


@app.task
def test_task(message="hello from celery"):
    print(f"[{time.strftime('%X')}] Task started. Schema: {connection.schema_name}")
    print(Employee.objects.all())
    time.sleep(2)  # simulate work, so you can see it's actually async
    print(f"[{time.strftime('%X')}] Task finished: {message}")
    return f"Done: {message}"


@app.task
def device_user_create_all_task(employee_id: int) -> None:
    from companies.models import Device

    employee = Employee.objects.get(pk=employee_id)
    devices = Device.objects.filter(
        company__schema_name=connection.schema_name,
        is_active=True,
    )
    if employee.branch_id:
        devices = devices.filter(branch_id=employee.branch_id)
    for serial_number in devices.values_list("serial_number", flat=True):
        device_user_create_task.delay(employee_id, serial_number)


@app.task(
    bind=True,
    autoretry_for=(HTTPError, URLError, TimeoutError, OSError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def device_user_create_task(self, employee_id: int, serial_number: str) -> None:
    from employees.services import device_user_create

    employee = Employee.objects.get(pk=employee_id)
    try:
        device_user_create(employee=employee, serial_number=serial_number)
    except ValidationError as exc:
        # Retry transient gateway ValidationErrors (502 etc.) if wrapped as ValidationError
        msg_dict = getattr(exc, "message_dict", {}) or {}
        gateway_msgs = msg_dict.get("device", []) or msg_dict.get("device_gateway", [])
        joined = " ".join(gateway_msgs) if isinstance(gateway_msgs, list) else str(gateway_msgs)
        check_str = joined or str(exc)
        is_transient = any(
            code in check_str
            for code in ("502", "503", "504", "500", "Gateway unreachable", "unreachable", "timeout", "timed out")
        )
        if is_transient and ("device" in msg_dict or "device_gateway" in msg_dict):
            raise self.retry(exc=exc)
        raise
