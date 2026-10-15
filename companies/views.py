from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import ProtectedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from common.http import (
    delete_blocked_response,
    is_htmx_partial,
    redirect_to_list_drawer,
    set_hx_trigger,
)
from common.pagination import list_pagination_context
from companies.forms import BranchForm, DeviceForm
from companies.models import Branch, Company, Device
from companies.selectors import branch_list, device_list
from companies.services import (
    branch_create,
    branch_delete,
    branch_update,
    device_create,
    device_delete,
    device_update,
)
from employees.decorators import require_permission
from employees.permission_catalog import PermissionCodename
from employees.selectors import user_has_permission


def _current_company(request: HttpRequest) -> Company | None:
    tenant = getattr(connection, "tenant", None)
    if tenant is None:
        tenant = getattr(request, "tenant", None)
    if isinstance(tenant, Company):
        return tenant
    try:
        return Company.objects.filter(schema_name=connection.schema_name).first()
    except Exception:
        return None


def _device_tabs_context(active: str) -> dict:
    return {"device_tab": active}


def _render_device_form(request, form, *, success_message=""):
    return render(
        request,
        "devices/device_add.html#device_form",
        {"form": form, "success_message": success_message},
    )


def _render_device_edit_form(request, form, *, device):
    return render(
        request,
        "devices/device_edit.html#device_edit_form",
        {"form": form, "device": device},
    )


def _render_branch_form(request, form, *, success_message=""):
    return render(
        request,
        "devices/branch_add.html#branch_form",
        {"form": form, "success_message": success_message},
    )


def _render_branch_edit_form(request, form, *, branch):
    return render(
        request,
        "devices/branch_edit.html#branch_edit_form",
        {"form": form, "branch": branch},
    )


@login_required
@require_permission(PermissionCodename.DEVICES_VIEW)
@require_http_methods(["GET"])
def device_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        device_list(search=search),
        search=search,
        base_url=reverse("device_list"),
        hx_target="#device-list",
    )
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.DEVICES_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.DEVICES_DELETE
    )
    context["can_view_branches"] = user_has_permission(
        user=request.user, codename=PermissionCodename.BRANCHES_VIEW
    )
    context.update(_device_tabs_context("devices"))

    if is_htmx_partial(request):
        return render(request, "devices/list.html#device_table", context)
    return render(request, "devices/list.html", context)


@login_required
@require_permission(PermissionCodename.DEVICES_ADD)
@require_http_methods(["GET", "POST"])
def device_add(request: HttpRequest) -> HttpResponse:
    company = _current_company(request)
    if company is None:
        form = DeviceForm(request.POST or None)
        return _render_device_form(request, form)

    if request.method == "POST":
        form = DeviceForm(request.POST, company=company)
        if form.is_valid():
            device_create(company=company, **form.cleaned_data)
            response = _render_device_form(
                request,
                DeviceForm(company=company),
                success_message=(
                    f"Device “{form.cleaned_data['serial_number']}” created."
                ),
            )
            set_hx_trigger(
                response,
                event="deviceCreated",
                toast=f"Device “{form.cleaned_data['serial_number']}” created.",
            )
            return response
        return _render_device_form(request, form)

    form = DeviceForm(company=company)
    if is_htmx_partial(request):
        return _render_device_form(request, form)
    return redirect_to_list_drawer(
        list_url_name="device_list",
        form_url=reverse("device_add"),
        title="Add device",
    )


@login_required
@require_permission(PermissionCodename.DEVICES_ADD)
@require_http_methods(["GET", "POST"])
def device_edit(request: HttpRequest, device_id: int) -> HttpResponse:
    company = _current_company(request)
    device = (
        Device.objects.select_related("company", "branch", "device_type__brand")
        .filter(pk=device_id)
        .first()
    )
    if device is None or (company is not None and device.company_id != company.id):
        from django.http import Http404

        raise Http404

    if request.method == "POST":
        form = DeviceForm(request.POST, instance=device, company=company)
        if form.is_valid():
            device_update(device=device, **form.cleaned_data)
            response = _render_device_edit_form(
                request, DeviceForm(instance=device, company=company), device=device
            )
            set_hx_trigger(response, event="deviceUpdated", toast="Device updated.")
            return response
        return _render_device_edit_form(request, form, device=device)

    form = DeviceForm(instance=device, company=company)
    if is_htmx_partial(request):
        return _render_device_edit_form(request, form, device=device)
    return redirect_to_list_drawer(
        list_url_name="device_list",
        form_url=request.path,
        title="Edit device",
    )


@login_required
@require_permission(PermissionCodename.DEVICES_DELETE)
@require_http_methods(["DELETE"])
def device_delete_view(request: HttpRequest, device_id: int) -> HttpResponse:
    company = _current_company(request)
    device = Device.objects.filter(pk=device_id).first()
    if device is None or (company is not None and device.company_id != company.id):
        from django.http import Http404

        raise Http404
    try:
        device_delete(device=device)
    except ProtectedError:
        return delete_blocked_response("Cannot delete: device is still referenced.")
    response = HttpResponse("")
    response["HX-Trigger"] = "deviceDeleted"
    return response


@login_required
@require_permission(PermissionCodename.BRANCHES_VIEW)
@require_http_methods(["GET"])
def branch_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        branch_list(search=search),
        search=search,
        base_url=reverse("branch_list"),
        hx_target="#branch-list",
    )
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.BRANCHES_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.BRANCHES_DELETE
    )
    context["can_view_devices"] = user_has_permission(
        user=request.user, codename=PermissionCodename.DEVICES_VIEW
    )
    context.update(_device_tabs_context("branches"))

    if is_htmx_partial(request):
        return render(request, "devices/branch_list.html#branch_table", context)
    return render(request, "devices/branch_list.html", context)


@login_required
@require_permission(PermissionCodename.BRANCHES_ADD)
@require_http_methods(["GET", "POST"])
def branch_add(request: HttpRequest) -> HttpResponse:
    company = _current_company(request)

    if request.method == "POST":
        form = BranchForm(request.POST)
        if form.is_valid():
            if company is None:
                form.add_error(None, "No company context.")
                return _render_branch_form(request, form)
            branch_create(company=company, **form.cleaned_data)
            response = _render_branch_form(
                request,
                BranchForm(),
                success_message=f"Branch “{form.cleaned_data['name']}” created.",
            )
            set_hx_trigger(
                response,
                event="branchCreated",
                toast=f"Branch “{form.cleaned_data['name']}” created.",
            )
            return response
        return _render_branch_form(request, form)

    form = BranchForm()
    if is_htmx_partial(request):
        return _render_branch_form(request, form)
    return redirect_to_list_drawer(
        list_url_name="branch_list",
        form_url=reverse("branch_add"),
        title="Add branch",
    )


@login_required
@require_permission(PermissionCodename.BRANCHES_ADD)
@require_http_methods(["GET", "POST"])
def branch_edit(request: HttpRequest, branch_id: int) -> HttpResponse:
    company = _current_company(request)
    branch = Branch.objects.filter(pk=branch_id).first()
    if branch is None or (company is not None and branch.company_id != company.id):
        from django.http import Http404

        raise Http404

    if request.method == "POST":
        form = BranchForm(request.POST, instance=branch)
        if form.is_valid():
            branch_update(branch=branch, **form.cleaned_data)
            response = _render_branch_edit_form(
                request, BranchForm(instance=branch), branch=branch
            )
            set_hx_trigger(response, event="branchUpdated", toast="Branch updated.")
            return response
        return _render_branch_edit_form(request, form, branch=branch)

    form = BranchForm(instance=branch)
    if is_htmx_partial(request):
        return _render_branch_edit_form(request, form, branch=branch)
    return redirect_to_list_drawer(
        list_url_name="branch_list",
        form_url=request.path,
        title="Edit branch",
    )


@login_required
@require_permission(PermissionCodename.BRANCHES_DELETE)
@require_http_methods(["DELETE"])
def branch_delete_view(request: HttpRequest, branch_id: int) -> HttpResponse:
    company = _current_company(request)
    branch = Branch.objects.filter(pk=branch_id).first()
    if branch is None or (company is not None and branch.company_id != company.id):
        from django.http import Http404

        raise Http404
    try:
        branch_delete(branch=branch)
    except ProtectedError:
        return delete_blocked_response(
            "Cannot delete: a device or employee still uses this branch."
        )
    response = HttpResponse("")
    response["HX-Trigger"] = "branchDeleted"
    return response
