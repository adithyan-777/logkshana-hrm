from django.db import transaction

from employees.models import Department, Employee, Permission, Position, Role

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
from django_tenants.utils import get_public_schema_name, schema_context
from tenant_users.tenants.utils import get_current_tenant
from users.models import TenantUser

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
    branch=None,
    email: str = "",
    mobile: str = "",
    hire_date=None,
    is_active: bool = True,
    sync_to_device: bool = True,
) -> Employee:
    """Creates the Employee's User account with an auto-generated username
    and the mobile number as the initial password. Mobile is required.
    Returns the employee. The invite link flow can still be used to let the
    employee set a new password afterwards.
    """
    tenant = get_current_tenant()
    mobile = (mobile or "").strip()
    if not mobile:
        raise ValidationError({"mobile": "Mobile number is required."})
    username = _generate_username(first_name=first_name, last_name=last_name)
    user_email = email or f"{username}@{tenant.slug}.com"
    with schema_context(get_public_schema_name()):
        user = TenantUser.objects.create_user(
            email=user_email,
            username=username,
            password=mobile,
            is_active=True,
        )

    tenant = get_current_tenant()
    tenant.add_user(user, is_superuser=False, is_staff=False)
    employee = Employee(
        user=user,
        first_name=first_name,
        last_name=last_name,
        emp_code=emp_code or None,
        department=department,
        position=position,
        branch=branch,
        email=email,
        mobile=mobile,
        hire_date=hire_date,
        is_active=is_active,
        role=employee_role_ensure(),
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


@transaction.atomic
def employee_update(
    *,
    employee: Employee,
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
    old_emp_code = employee.emp_code
    employee.first_name = first_name
    employee.last_name = last_name
    employee.emp_code = emp_code or None
    employee.department = department
    employee.position = position
    employee.email = email
    employee.mobile = mobile
    employee.hire_date = hire_date
    employee.is_active = is_active
    employee.full_clean()
    employee.save()

    user = employee.user
    if user is not None:
        user_updates: list[str] = []
        if email and user.email != email:
            user.email = email
            user_updates.append("email")
        if user.is_active != is_active:
            user.is_active = is_active
            user_updates.append("is_active")
        if user_updates:
            with schema_context(get_public_schema_name()):
                user.save(update_fields=user_updates)

    if sync_to_device and employee.emp_code and employee.emp_code != old_emp_code:
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


@transaction.atomic
def employee_delete(*, employee: Employee) -> Employee:
    """Soft-deletes the employee and deactivates their login account."""
    user = employee.user
    employee.delete()
    if user is not None and user.is_active:
        with schema_context(get_public_schema_name()):
            user.is_active = False
            user.save(update_fields=["is_active"])
    return employee


@transaction.atomic
def department_update(
    *,
    department: Department,
    name: str,
    code: str = "",
    parent: Department | None = None,
) -> Department:
    department.name = name
    department.code = code or None
    department.parent = parent
    department.full_clean()
    department.save()
    return department


@transaction.atomic
def department_delete(*, department: Department) -> Department:
    """Soft-deletes the department (recoverable via all_objects)."""
    department.delete()
    return department


@transaction.atomic
def position_update(
    *,
    position: Position,
    title: str,
    code: str = "",
    parent: Position | None = None,
) -> Position:
    position.title = title
    position.code = code or None
    position.parent = parent
    position.full_clean()
    position.save()
    return position


@transaction.atomic
def position_delete(*, position: Position) -> Position:
    """Soft-deletes the position (recoverable via all_objects)."""
    position.delete()
    return position


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
    from attendance.integrations.gateway import gateway_auth_headers

    request = Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", **gateway_auth_headers()},
    )
    try:
        with urlopen(request, timeout=15) as response:
            response.read()
    except HTTPError as exc:
        if 500 <= exc.code < 600:
            # Transient 5xx (502 etc.) — let caller retry (Celery autoretry)
            try:
                body = exc.read().decode(errors="ignore")[:500] if hasattr(exc, "read") else ""
            except Exception:
                body = ""
            detail = f" body: {body}" if body else ""
            raise HTTPError(
                exc.url, exc.code, f"{exc.msg} for {url}.{detail} (base: {settings.DEVICE_GATEWAY_BASE_URL})",
                exc.headers, exc.fp
            ) from exc
        try:
            body = exc.read().decode(errors="ignore")[:500] if hasattr(exc, "read") else ""
        except Exception:
            body = ""
        detail = f" body: {body}" if body else ""
        raise ValidationError({"device": f"Gateway returned HTTP {exc.code}.{detail} for {url}"}) from exc
    except (URLError, TimeoutError, OSError) as exc:
        # Transient — re-raise for retry
        if isinstance(exc, URLError):
            raise URLError(f"Gateway unreachable at {settings.DEVICE_GATEWAY_BASE_URL} ({url}): {exc.reason}") from exc
        raise


@transaction.atomic
def department_create(
    *,
    name: str,
    code: str = "",
    parent: Department | None = None,
) -> Department:
    department = Department(name=name, code=code or None, parent=parent)
    department.full_clean()
    department.save()
    return department


@transaction.atomic
def position_create(
    *,
    title: str,
    code: str = "",
    parent: Position | None = None,
) -> Position:
    position = Position(title=title, code=code or None, parent=parent)
    position.full_clean()
    position.save()
    return position


@transaction.atomic
def permission_catalog_ensure() -> list[Permission]:
    from employees.permission_catalog import permission_catalog_entries

    permissions: list[Permission] = []
    for entry in permission_catalog_entries():
        permission, _created = Permission.all_objects.update_or_create(
            codename=entry["codename"],
            defaults={
                "name": entry["name"],
                "description": entry["description"],
                "deleted_at": None,
            },
        )
        permissions.append(permission)
    return permissions


@transaction.atomic
def employee_role_ensure() -> Role:
    from employees.permission_catalog import (
        EMPLOYEE_ROLE_NAME,
        PermissionCodename,
    )

    permission_catalog_ensure()
    permission = Permission.objects.get(codename=PermissionCodename.ATTENDANCE_OWN_VIEW)
    role, _created = Role.all_objects.update_or_create(
        name=EMPLOYEE_ROLE_NAME,
        defaults={"is_system": True, "deleted_at": None},
    )
    role.permissions.set([permission])
    return role


def employees_assign_employee_role() -> int:
    from django.db.models import Q
    from tenant_users.permissions.models import UserTenantPermissions

    role = employee_role_ensure()
    admin_user_ids = set(
        UserTenantPermissions.objects.filter(
            Q(is_staff=True) | Q(is_superuser=True)
        ).values_list("profile_id", flat=True)
    )
    tenant = getattr(connection, "tenant", None)
    owner_id = getattr(tenant, "owner_id", None) if tenant is not None else None
    if owner_id:
        admin_user_ids.add(owner_id)

    return (
        Employee.objects.filter(user__isnull=False)
        .exclude(user_id__in=admin_user_ids)
        .update(role=role)
    )


@transaction.atomic
def permission_create(
    *,
    codename: str,
    name: str,
    description: str = "",
) -> Permission:
    permission = Permission(codename=codename, name=name, description=description)
    permission.full_clean()
    permission.save()
    return permission


@transaction.atomic
def role_create(
    *,
    name: str,
    is_system: bool = False,
    permissions: list[Permission] | None = None,
) -> Role:
    role = Role(name=name, is_system=is_system)
    role.full_clean()
    role.save()
    if permissions:
        role.permissions.set(permissions)
    return role
