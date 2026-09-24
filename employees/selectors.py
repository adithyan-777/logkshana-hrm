from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Q, QuerySet

from employees.models import Department, Employee, Permission, Position, Role


def employee_list(*, search: str = "") -> QuerySet[Employee]:
    queryset = Employee.objects.select_related(
        "department", "position", "user"
    ).order_by("-id")

    if search:
        queryset = queryset.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(emp_code__icontains=search)
            | Q(email__icontains=search)
        )

    return queryset


def employee_get_by_emp_code(*, emp_code: str) -> Employee | None:
    matches = list(Employee.objects.filter(emp_code=emp_code, is_active=True)[:2])
    if len(matches) > 1:
        raise ValidationError(
            {"employee_id": "Multiple employees found for this employee id."}
        )
    if not matches:
        return None
    return matches[0]


def employee_get(*, employee_id: int) -> Employee | None:
    return (
        Employee.objects.select_related("department", "position", "user", "role")
        .filter(pk=employee_id)
        .first()
    )


def department_list(*, search: str = "") -> QuerySet[Department]:
    queryset = Department.objects.select_related("parent").order_by("name")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )

    return queryset


def position_list(*, search: str = "") -> QuerySet[Position]:
    queryset = Position.objects.select_related("parent").order_by("title")

    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) | Q(code__icontains=search)
        )

    return queryset


def role_list(*, search: str = "") -> QuerySet[Role]:
    queryset = Role.objects.order_by("name")

    if search:
        queryset = queryset.filter(Q(name__icontains=search))

    return queryset


def permission_list(*, search: str = "") -> QuerySet[Permission]:
    queryset = Permission.objects.order_by("codename")

    if search:
        queryset = queryset.filter(
            Q(codename__icontains=search)
            | Q(name__icontains=search)
            | Q(description__icontains=search)
        )

    return queryset


def user_is_admin(*, user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    tenant = getattr(connection, "tenant", None)
    owner_id = getattr(tenant, "owner_id", None) if tenant is not None else None
    return bool(owner_id and getattr(user, "pk", None) == owner_id)


def user_has_permission(*, user, codename: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if user_is_admin(user=user):
        return True
    user_pk = getattr(user, "pk", None)
    if user_pk is None:
        return False
    return Employee.objects.filter(
        user_id=user_pk,
        role__permissions__codename=codename,
    ).exists()


def employee_get_for_user(*, user) -> Employee | None:
    user_pk = getattr(user, "pk", None)
    if user_pk is None:
        return None
    return Employee.objects.filter(user_id=user_pk).first()


def user_permission_codenames(*, user) -> frozenset[str] | None:
    """Granted permission codenames, or None when the user is an admin."""
    if not getattr(user, "is_authenticated", False):
        return frozenset()
    if user_is_admin(user=user):
        return None
    user_pk = getattr(user, "pk", None)
    if user_pk is None:
        return frozenset()
    return frozenset(
        codename
        for codename in Employee.objects.filter(user_id=user_pk).values_list(
            "role__permissions__codename",
            flat=True,
        )
        if codename
    )
