from django.db import transaction

from employees.models import Employee
import secrets
import string

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.text import slugify

from allauth.account.forms import default_token_generator
from allauth.account.utils import user_pk_to_url_str
from django.urls import reverse

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
) -> Employee:
    """Creates the Employee's User account with an auto-generated username
    and temporary password. Returns (employee, plaintext_password) — the
    plaintext is only available here, at creation time; show it to the admin
    once (e.g. in the response / a one-time confirmation screen) or email it
    to the employee. Never store it.
    """
    username = _generate_username(first_name=first_name, last_name=last_name)

    user = User(username=username, email=email)
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
    return employee


def employee_invite_link(*, employee: Employee, request) -> str:
    user = employee.user
    key = default_token_generator.make_token(user)
    path = reverse(
        "account_reset_password_from_key",
        kwargs={"uidb36": user_pk_to_url_str(user), "key": key},
    )
    return request.build_absolute_uri(path)
