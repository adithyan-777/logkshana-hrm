import time
from django.db import connection
from config.celery import app
from employees.models import Employee
from urllib.error import URLError
from config.celery import app


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
    autoretry_for=(URLError, TimeoutError, OSError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def device_user_create_task(self, employee_id: int, serial_number: str) -> None:
    from employees.services import device_user_create
    employee = Employee.objects.get(pk=employee_id)
    device_user_create(employee=employee, serial_number=serial_number)