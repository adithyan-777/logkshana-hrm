from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from common.http import is_htmx_partial
from common.pagination import list_pagination_context
from employees.decorators import require_permission
from employees.forms import (
    DepartmentForm,
    EmployeeForm,
    PermissionForm,
    PositionForm,
    RoleForm,
)
from employees.models import Department, Employee, Position
from employees.permission_catalog import PermissionCodename
from employees.selectors import (
    department_list,
    employee_get,
    employee_list,
    permission_list,
    position_list,
    role_list,
    user_has_permission,
)
from employees.services import (
    department_create,
    department_delete,
    department_update,
    employee_create,
    employee_delete,
    employee_invite_link,
    employee_role_ensure,
    employee_update,
    permission_catalog_ensure,
    permission_create,
    position_create,
    position_delete,
    position_update,
    role_create,
)


def _render_form(
    request: HttpRequest, form: EmployeeForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "employees/add.html#employee_form",
        {"form": form, "success_message": success_message},
    )


def _render_invite(request: HttpRequest, employee, invite_link: str) -> HttpResponse:
    return render(
        request,
        "employees/add.html#employee_invite",
        {"employee": employee, "invite_link": invite_link},
    )


@login_required
@require_permission(PermissionCodename.EMPLOYEES_VIEW)
@require_http_methods(["GET"])
def employee_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        employee_list(search=search),
        search=search,
        base_url=reverse("employee_list"),
        hx_target="#employee-list",
    )
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.EMPLOYEES_EDIT
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.EMPLOYEES_DELETE
    )

    if is_htmx_partial(request):
        return render(request, "employees/list.html#employee_table", context)

    return render(request, "employees/list.html", context)


@login_required
@require_permission(PermissionCodename.EMPLOYEES_ADD)
@require_http_methods(["GET", "POST"])
def employee_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = employee_create(**form.cleaned_data)
            invite_link = employee_invite_link(employee=employee, request=request)

            response = _render_invite(request, employee, invite_link)
            response["HX-Trigger"] = "employeeCreated"
            return response

        return _render_form(request, form)

    form = EmployeeForm()
    if is_htmx_partial(request):
        return _render_form(request, form)

    return render(request, "employees/add.html", {"form": form})


def _render_edit_form(
    request: HttpRequest,
    form: EmployeeForm,
    *,
    employee: Employee,
    success_message: str = "",
) -> HttpResponse:
    return render(
        request,
        "employees/edit.html#employee_edit_form",
        {
            "form": form,
            "employee": employee,
            "success_message": success_message,
        },
    )


@login_required
@require_permission(PermissionCodename.EMPLOYEES_EDIT)
@require_http_methods(["GET", "POST"])
def employee_edit(request: HttpRequest, employee_id: int) -> HttpResponse:
    employee = employee_get(employee_id=employee_id)
    if employee is None:
        raise Http404

    if request.method == "POST":
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            employee_update(**form.cleaned_data, employee=employee)
            response = _render_edit_form(
                request,
                EmployeeForm(instance=employee),
                employee=employee,
                success_message=f"Employee “{employee.full_name}” updated.",
            )
            response["HX-Trigger"] = "employeeUpdated"
            return response

        return _render_edit_form(request, form, employee=employee)

    form = EmployeeForm(instance=employee)
    if is_htmx_partial(request):
        return _render_edit_form(request, form, employee=employee)

    return render(
        request,
        "employees/edit.html",
        {"form": form, "employee": employee},
    )


@login_required
@require_permission(PermissionCodename.EMPLOYEES_DELETE)
@require_http_methods(["DELETE"])
def employee_delete_view(request: HttpRequest, employee_id: int) -> HttpResponse:
    employee = employee_get(employee_id=employee_id)
    if employee is None:
        raise Http404
    employee_delete(employee=employee)
    response = HttpResponse("")
    response["HX-Trigger"] = "employeeDeleted"
    return response


def _render_department_form(
    request: HttpRequest, form: DepartmentForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "employees/department_add.html#department_form",
        {"form": form, "success_message": success_message},
    )


@login_required
@require_permission(PermissionCodename.DEPARTMENTS_VIEW)
@require_http_methods(["GET"])
def department_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        department_list(search=search),
        search=search,
        base_url=reverse("department_list"),
        hx_target="#department-list",
    )
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.DEPARTMENTS_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.DEPARTMENTS_DELETE
    )

    if is_htmx_partial(request):
        return render(
            request, "employees/department_list.html#department_table", context
        )

    return render(request, "employees/department_list.html", context)


@login_required
@require_permission(PermissionCodename.DEPARTMENTS_ADD)
@require_http_methods(["GET", "POST"])
def department_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department_create(**form.cleaned_data)
            response = _render_department_form(
                request,
                DepartmentForm(),
                success_message=f"Department “{form.cleaned_data['name']}” created.",
            )
            response["HX-Trigger"] = "departmentCreated"
            return response

        return _render_department_form(request, form)

    form = DepartmentForm()
    if is_htmx_partial(request):
        return _render_department_form(request, form)

    return render(request, "employees/department_add.html", {"form": form})


def _render_department_edit_form(
    request: HttpRequest, form: DepartmentForm, *, department: Department
) -> HttpResponse:
    return render(
        request,
        "employees/department_edit.html#department_edit_form",
        {"form": form, "department": department},
    )


@login_required
@require_permission(PermissionCodename.DEPARTMENTS_ADD)
@require_http_methods(["GET", "POST"])
def department_edit(request: HttpRequest, department_id: int) -> HttpResponse:
    department = get_object_or_404(Department, pk=department_id)

    if request.method == "POST":
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            department_update(**form.cleaned_data, department=department)
            response = _render_department_edit_form(
                request, DepartmentForm(instance=department), department=department
            )
            response["HX-Trigger"] = "departmentUpdated"
            return response

        return _render_department_edit_form(request, form, department=department)

    form = DepartmentForm(instance=department)
    if is_htmx_partial(request):
        return _render_department_edit_form(request, form, department=department)

    return render(
        request,
        "employees/department_edit.html",
        {"form": form, "department": department},
    )


@login_required
@require_permission(PermissionCodename.DEPARTMENTS_DELETE)
@require_http_methods(["DELETE"])
def department_delete_view(request: HttpRequest, department_id: int) -> HttpResponse:
    department = get_object_or_404(Department, pk=department_id)
    department_delete(department=department)
    response = HttpResponse("")
    response["HX-Trigger"] = "departmentDeleted"
    return response


def _render_position_form(
    request: HttpRequest, form: PositionForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "employees/position_add.html#position_form",
        {"form": form, "success_message": success_message},
    )


@login_required
@require_permission(PermissionCodename.POSITIONS_VIEW)
@require_http_methods(["GET"])
def position_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        position_list(search=search),
        search=search,
        base_url=reverse("position_list"),
        hx_target="#position-list",
    )
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.POSITIONS_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.POSITIONS_DELETE
    )

    if is_htmx_partial(request):
        return render(request, "employees/position_list.html#position_table", context)

    return render(request, "employees/position_list.html", context)


@login_required
@require_permission(PermissionCodename.POSITIONS_ADD)
@require_http_methods(["GET", "POST"])
def position_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = PositionForm(request.POST)
        if form.is_valid():
            position_create(**form.cleaned_data)
            response = _render_position_form(
                request,
                PositionForm(),
                success_message=f"Position “{form.cleaned_data['title']}” created.",
            )
            response["HX-Trigger"] = "positionCreated"
            return response

        return _render_position_form(request, form)

    form = PositionForm()
    if is_htmx_partial(request):
        return _render_position_form(request, form)

    return render(request, "employees/position_add.html", {"form": form})


def _render_position_edit_form(
    request: HttpRequest, form: PositionForm, *, position: Position
) -> HttpResponse:
    return render(
        request,
        "employees/position_edit.html#position_edit_form",
        {"form": form, "position": position},
    )


@login_required
@require_permission(PermissionCodename.POSITIONS_ADD)
@require_http_methods(["GET", "POST"])
def position_edit(request: HttpRequest, position_id: int) -> HttpResponse:
    position = get_object_or_404(Position, pk=position_id)

    if request.method == "POST":
        form = PositionForm(request.POST, instance=position)
        if form.is_valid():
            position_update(**form.cleaned_data, position=position)
            response = _render_position_edit_form(
                request, PositionForm(instance=position), position=position
            )
            response["HX-Trigger"] = "positionUpdated"
            return response

        return _render_position_edit_form(request, form, position=position)

    form = PositionForm(instance=position)
    if is_htmx_partial(request):
        return _render_position_edit_form(request, form, position=position)

    return render(
        request,
        "employees/position_edit.html",
        {"form": form, "position": position},
    )


@login_required
@require_permission(PermissionCodename.POSITIONS_DELETE)
@require_http_methods(["DELETE"])
def position_delete_view(request: HttpRequest, position_id: int) -> HttpResponse:
    position = get_object_or_404(Position, pk=position_id)
    position_delete(position=position)
    response = HttpResponse("")
    response["HX-Trigger"] = "positionDeleted"
    return response


def _render_role_form(
    request: HttpRequest, form: RoleForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "employees/role_add.html#role_form",
        {"form": form, "success_message": success_message},
    )


@login_required
@require_permission(PermissionCodename.ROLES_VIEW)
@require_http_methods(["GET"])
def role_list_view(request: HttpRequest) -> HttpResponse:
    employee_role_ensure()
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        role_list(search=search),
        search=search,
        base_url=reverse("role_list"),
        hx_target="#role-list",
    )

    if is_htmx_partial(request):
        return render(request, "employees/role_list.html#role_table", context)

    return render(request, "employees/role_list.html", context)


@login_required
@require_permission(PermissionCodename.ROLES_ADD)
@require_http_methods(["GET", "POST"])
def role_add(request: HttpRequest) -> HttpResponse:
    permission_catalog_ensure()
    if request.method == "POST":
        form = RoleForm(request.POST)
        if form.is_valid():
            role_create(
                name=form.cleaned_data["name"],
                permissions=list(form.cleaned_data.get("permissions", []) or []),
            )
            response = _render_role_form(
                request,
                RoleForm(),
                success_message=f"Role “{form.cleaned_data['name']}” created.",
            )
            response["HX-Trigger"] = "roleCreated"
            return response

        return _render_role_form(request, form)

    form = RoleForm()
    if is_htmx_partial(request):
        return _render_role_form(request, form)

    return render(request, "employees/role_add.html", {"form": form})


def _render_permission_form(
    request: HttpRequest, form: PermissionForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "employees/permission_add.html#permission_form",
        {"form": form, "success_message": success_message},
    )


@login_required
@require_permission(PermissionCodename.PERMISSIONS_VIEW)
@require_http_methods(["GET"])
def permission_list_view(request: HttpRequest) -> HttpResponse:
    permission_catalog_ensure()
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        permission_list(search=search),
        search=search,
        base_url=reverse("permission_list"),
        hx_target="#permission-list",
    )

    if is_htmx_partial(request):
        return render(
            request, "employees/permission_list.html#permission_table", context
        )

    return render(request, "employees/permission_list.html", context)


@login_required
@require_permission(PermissionCodename.PERMISSIONS_ADD)
@require_http_methods(["GET", "POST"])
def permission_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = PermissionForm(request.POST)
        if form.is_valid():
            permission_create(**form.cleaned_data)
            response = _render_permission_form(
                request,
                PermissionForm(),
                success_message=f"Permission “{form.cleaned_data['codename']}” created.",
            )
            response["HX-Trigger"] = "permissionCreated"
            return response

        return _render_permission_form(request, form)

    form = PermissionForm()
    if is_htmx_partial(request):
        return _render_permission_form(request, form)

    return render(request, "employees/permission_add.html", {"form": form})
