import time
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
