from django.db import transaction

from employees.models import Employee

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from django.conf import settings
from django.core.exceptions import ValidationError
from companies.selectors import device_get_by_serial_number

from django.contrib.auth import get_user_model
from django.db import transaction, connection
from django.utils.text import slugify

from allauth.account.forms import default_token_generator
from allauth.account.utils import user_pk_to_url_str
from django.urls import reverse
from companies.models import Device

from employees.tasks import device_user_create_task


User = get_user_model()


def _generate_username(*, first_name: str, last_name: str) -> str:
    base = slugify(f"{first_name}.{last_name}") or "employee"
    username = base
    suffix = 1
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base}{suffix}"
    return username


@transaction.atomic
def employee_create(
    *,
    first_name: str,
    last_name: str = "",
    emp_code: str | None = None,
    department=None,
    position=None,
    email: str = "",
    mobile: str = "",
    hire_date=None,
    is_active: bool = True,
    sync_to_device: bool = True,
) -> Employee:
    """Creates the Employee's User account with an auto-generated username
    and temporary password. Returns (employee, plaintext_password) — the
    plaintext is only available here, at creation time; show it to the admin
    once (e.g. in the response / a one-time confirmation screen) or email it
    to the employee. Never store it.
    """
    username = _generate_username(first_name=first_name, last_name=last_name)
    user_email = email or f"{username}@users.invalid"

    user = User(username=username, email=user_email)
    user.set_unusable_password()
    user.save()

    employee = Employee(
        user=user,
        first_name=first_name,
        last_name=last_name,
        emp_code=emp_code or None,
        department=department,
        position=position,
        email=email,
        mobile=mobile,
        hire_date=hire_date,
        is_active=is_active,
    )
    employee.full_clean()
    employee.save()

    if sync_to_device and employee.emp_code:
        employee_id = employee.id
        serials = list(
            Device.objects.filter(
                company__schema_name=connection.schema_name,
                is_active=True,
            ).values_list("serial_number", flat=True)
        )
        transaction.on_commit(
            lambda: [
                device_user_create_task.delay(employee_id, serial) for serial in serials
            ]
        )
    return employee


def employee_invite_link(*, employee: Employee, request) -> str:
    user = employee.user
    key = default_token_generator.make_token(user)
    path = reverse(
        "account_reset_password_from_key",
        kwargs={"uidb36": user_pk_to_url_str(user), "key": key},
    )
    return request.build_absolute_uri(path)


def device_user_create(*, employee: Employee, serial_number: str) -> None:
    if not employee.emp_code:
        raise ValidationError({"emp_code": "Employee has no emp_code (device PIN)."})
    device = device_get_by_serial_number(serial_number=serial_number)
    if device is None or not device.is_active:
        raise ValidationError({"serial_number": "Unknown or inactive device."})
    url = (
        f"{settings.DEVICE_GATEWAY_BASE_URL.rstrip('/')}"
        f"/api/devices/{serial_number}/users"
    )
    payload = {
        "pin": employee.emp_code,
        "name": employee.full_name,
        "privilege": 0,
        "card": "",
    }
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            response.read()
    except HTTPError as exc:
        raise ValidationError({"device": f"Gateway returned HTTP {exc.code}."}) from exc
    except URLError as exc:
        raise ValidationError({"device": "Gateway unreachable."}) from exc
