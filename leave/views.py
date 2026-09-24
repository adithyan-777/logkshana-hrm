from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from common.http import is_htmx_partial, redirect_to_list_drawer, set_hx_trigger
from common.pagination import list_pagination_context
from employees.decorators import require_permission
from employees.permission_catalog import PermissionCodename
from employees.selectors import user_has_permission
from leave.forms import (
    HolidayForm,
    LeavePolicyForm,
    LeaveRequestForm,
    LeaveTypeForm,
)
from leave.models import Holiday, LeavePolicy, LeaveRequest, LeaveType
from leave.selectors import (
    holiday_list,
    leave_policy_list,
    leave_request_list,
    leave_type_list,
)
from leave.services import (
    holiday_create,
    holiday_delete,
    holiday_update,
    leave_policy_create,
    leave_policy_delete,
    leave_policy_update,
    leave_request_create,
    leave_request_delete,
    leave_request_update,
    leave_type_create,
    leave_type_delete,
    leave_type_update,
)


def _render_leave_type_form(
    request: HttpRequest, form: LeaveTypeForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "leave/leave_type_add.html#leave_type_form",
        {"form": form, "success_message": success_message},
    )


def _render_leave_policy_form(
    request: HttpRequest, form: LeavePolicyForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "leave/leave_policy_add.html#leave_policy_form",
        {"form": form, "success_message": success_message},
    )


def _render_leave_request_form(
    request: HttpRequest, form: LeaveRequestForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "leave/leave_request_add.html#leave_request_form",
        {"form": form, "success_message": success_message},
    )


def _render_holiday_form(
    request: HttpRequest, form: HolidayForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "leave/holiday_add.html#holiday_form",
        {"form": form, "success_message": success_message},
    )


def _render_leave_type_edit_form(
    request: HttpRequest, form: LeaveTypeForm, *, leave_type: LeaveType
) -> HttpResponse:
    return render(
        request,
        "leave/leave_type_edit.html#leave_type_edit_form",
        {"form": form, "leave_type": leave_type},
    )


def _render_leave_policy_edit_form(
    request: HttpRequest, form: LeavePolicyForm, *, leave_policy: LeavePolicy
) -> HttpResponse:
    return render(
        request,
        "leave/leave_policy_edit.html#leave_policy_edit_form",
        {"form": form, "leave_policy": leave_policy},
    )


def _render_leave_request_edit_form(
    request: HttpRequest, form: LeaveRequestForm, *, leave_request: LeaveRequest
) -> HttpResponse:
    return render(
        request,
        "leave/leave_request_edit.html#leave_request_edit_form",
        {"form": form, "leave_request": leave_request},
    )


def _render_holiday_edit_form(
    request: HttpRequest, form: HolidayForm, *, holiday: Holiday
) -> HttpResponse:
    return render(
        request,
        "leave/holiday_edit.html#holiday_edit_form",
        {"form": form, "holiday": holiday},
    )


@login_required
@require_permission(PermissionCodename.LEAVE_TYPES_MANAGE)
@require_http_methods(["GET"])
def leave_type_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        leave_type_list(search=search),
        search=search,
        base_url=reverse("leave_type_list"),
        hx_target="#leave-type-list",
    )
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.LEAVE_TYPES_MANAGE
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.LEAVE_DELETE
    )

    if is_htmx_partial(request):
        return render(request, "leave/leave_type_list.html#leave_type_table", context)

    return render(request, "leave/leave_type_list.html", context)


@login_required
@require_permission(PermissionCodename.LEAVE_TYPES_MANAGE)
@require_http_methods(["GET", "POST"])
def leave_type_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = LeaveTypeForm(request.POST)
        if form.is_valid():
            leave_type_create(**form.cleaned_data)
            response = _render_leave_type_form(
                request,
                LeaveTypeForm(),
                success_message=f"Leave type “{form.cleaned_data['name']}” created.",
            )
            set_hx_trigger(
                response,
                event="leaveTypeCreated",
                toast=f"Leave type “{form.cleaned_data['name']}” created.",
            )
            return response

        return _render_leave_type_form(request, form)

    form = LeaveTypeForm()
    if is_htmx_partial(request):
        return _render_leave_type_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="leave_type_list",
        form_url=reverse("leave_type_add"),
        title="Add leave type",
    )


@login_required
@require_permission(PermissionCodename.LEAVE_TYPES_MANAGE)
@require_http_methods(["GET", "POST"])
def leave_type_edit(request: HttpRequest, leave_type_id: int) -> HttpResponse:
    leave_type = get_object_or_404(LeaveType, pk=leave_type_id)

    if request.method == "POST":
        form = LeaveTypeForm(request.POST, instance=leave_type)
        if form.is_valid():
            leave_type_update(**form.cleaned_data, leave_type=leave_type)
            response = _render_leave_type_edit_form(
                request, LeaveTypeForm(instance=leave_type), leave_type=leave_type
            )
            response["HX-Trigger"] = "leaveTypeUpdated"
            return response

        return _render_leave_type_edit_form(request, form, leave_type=leave_type)

    form = LeaveTypeForm(instance=leave_type)
    if is_htmx_partial(request):
        return _render_leave_type_edit_form(request, form, leave_type=leave_type)

    return redirect_to_list_drawer(
        list_url_name="leave_type_list",
        form_url=request.path,
        title="Edit leave type",
    )


@login_required
@require_permission(PermissionCodename.LEAVE_DELETE)
@require_http_methods(["DELETE"])
def leave_type_delete_view(request: HttpRequest, leave_type_id: int) -> HttpResponse:
    leave_type = get_object_or_404(LeaveType, pk=leave_type_id)
    leave_type_delete(leave_type=leave_type)
    response = HttpResponse("")
    response["HX-Trigger"] = "leaveTypeDeleted"
    return response


@login_required
@require_permission(PermissionCodename.LEAVE_TYPES_MANAGE)
@require_http_methods(["GET"])
def leave_policy_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        leave_policy_list(search=search),
        search=search,
        base_url=reverse("leave_policy_list"),
        hx_target="#leave-policy-list",
    )
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.LEAVE_TYPES_MANAGE
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.LEAVE_DELETE
    )

    if is_htmx_partial(request):
        return render(
            request, "leave/leave_policy_list.html#leave_policy_table", context
        )

    return render(request, "leave/leave_policy_list.html", context)


@login_required
@require_permission(PermissionCodename.LEAVE_TYPES_MANAGE)
@require_http_methods(["GET", "POST"])
def leave_policy_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = LeavePolicyForm(request.POST)
        if form.is_valid():
            leave_policy_create(**form.cleaned_data)
            response = _render_leave_policy_form(
                request,
                LeavePolicyForm(),
                success_message=f"Leave policy “{form.cleaned_data['name']}” created.",
            )
            set_hx_trigger(
                response,
                event="leavePolicyCreated",
                toast=f"Leave policy “{form.cleaned_data['name']}” created.",
            )
            return response

        return _render_leave_policy_form(request, form)

    form = LeavePolicyForm()
    if is_htmx_partial(request):
        return _render_leave_policy_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="leave_policy_list",
        form_url=reverse("leave_policy_add"),
        title="Add leave policy",
    )


@login_required
@require_permission(PermissionCodename.LEAVE_TYPES_MANAGE)
@require_http_methods(["GET", "POST"])
def leave_policy_edit(request: HttpRequest, leave_policy_id: int) -> HttpResponse:
    leave_policy = get_object_or_404(LeavePolicy, pk=leave_policy_id)

    if request.method == "POST":
        form = LeavePolicyForm(request.POST, instance=leave_policy)
        if form.is_valid():
            leave_policy_update(**form.cleaned_data, leave_policy=leave_policy)
            response = _render_leave_policy_edit_form(
                request,
                LeavePolicyForm(instance=leave_policy),
                leave_policy=leave_policy,
            )
            response["HX-Trigger"] = "leavePolicyUpdated"
            return response

        return _render_leave_policy_edit_form(request, form, leave_policy=leave_policy)

    form = LeavePolicyForm(instance=leave_policy)
    if is_htmx_partial(request):
        return _render_leave_policy_edit_form(request, form, leave_policy=leave_policy)

    return redirect_to_list_drawer(
        list_url_name="leave_policy_list",
        form_url=request.path,
        title="Edit leave policy",
    )


@login_required
@require_permission(PermissionCodename.LEAVE_DELETE)
@require_http_methods(["DELETE"])
def leave_policy_delete_view(
    request: HttpRequest, leave_policy_id: int
) -> HttpResponse:
    leave_policy = get_object_or_404(LeavePolicy, pk=leave_policy_id)
    leave_policy_delete(leave_policy=leave_policy)
    response = HttpResponse("")
    response["HX-Trigger"] = "leavePolicyDeleted"
    return response


@login_required
@require_permission(PermissionCodename.LEAVE_VIEW)
@require_http_methods(["GET"])
def leave_request_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        leave_request_list(search=search),
        search=search,
        base_url=reverse("leave_request_list"),
        hx_target="#leave-request-list",
    )
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.LEAVE_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.LEAVE_DELETE
    )

    if is_htmx_partial(request):
        return render(
            request, "leave/leave_request_list.html#leave_request_table", context
        )

    return render(request, "leave/leave_request_list.html", context)


@login_required
@require_permission(PermissionCodename.LEAVE_ADD)
@require_http_methods(["GET", "POST"])
def leave_request_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request_create(**form.cleaned_data, created_by=request.user)
            response = _render_leave_request_form(
                request,
                LeaveRequestForm(),
                success_message="Leave request created.",
            )
            set_hx_trigger(
                response,
                event="leaveRequestCreated",
                toast="Leave request created.",
            )
            return response

        return _render_leave_request_form(request, form)

    form = LeaveRequestForm()
    if is_htmx_partial(request):
        return _render_leave_request_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="leave_request_list",
        form_url=reverse("leave_request_add"),
        title="Add leave request",
    )


@login_required
@require_permission(PermissionCodename.LEAVE_ADD)
@require_http_methods(["GET", "POST"])
def leave_request_edit(request: HttpRequest, leave_request_id: int) -> HttpResponse:
    leave_request = get_object_or_404(LeaveRequest, pk=leave_request_id)

    if request.method == "POST":
        form = LeaveRequestForm(request.POST, instance=leave_request)
        if form.is_valid():
            leave_request_update(**form.cleaned_data, leave_request=leave_request)
            response = _render_leave_request_edit_form(
                request,
                LeaveRequestForm(instance=leave_request),
                leave_request=leave_request,
            )
            response["HX-Trigger"] = "leaveRequestUpdated"
            return response

        return _render_leave_request_edit_form(
            request, form, leave_request=leave_request
        )

    form = LeaveRequestForm(instance=leave_request)
    if is_htmx_partial(request):
        return _render_leave_request_edit_form(
            request, form, leave_request=leave_request
        )

    return redirect_to_list_drawer(
        list_url_name="leave_request_list",
        form_url=request.path,
        title="Edit leave request",
    )


@login_required
@require_permission(PermissionCodename.LEAVE_DELETE)
@require_http_methods(["DELETE"])
def leave_request_delete_view(
    request: HttpRequest, leave_request_id: int
) -> HttpResponse:
    leave_request = get_object_or_404(LeaveRequest, pk=leave_request_id)
    leave_request_delete(leave_request=leave_request)
    response = HttpResponse("")
    response["HX-Trigger"] = "leaveRequestDeleted"
    return response


@login_required
@require_permission(PermissionCodename.LEAVE_HOLIDAYS_MANAGE)
@require_http_methods(["GET"])
def holiday_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        holiday_list(search=search),
        search=search,
        base_url=reverse("holiday_list"),
        hx_target="#holiday-list",
    )
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.LEAVE_HOLIDAYS_MANAGE
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.LEAVE_DELETE
    )

    if is_htmx_partial(request):
        return render(request, "leave/holiday_list.html#holiday_table", context)

    return render(request, "leave/holiday_list.html", context)


@login_required
@require_permission(PermissionCodename.LEAVE_HOLIDAYS_MANAGE)
@require_http_methods(["GET", "POST"])
def holiday_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = HolidayForm(request.POST)
        if form.is_valid():
            holiday_create(**form.cleaned_data)
            response = _render_holiday_form(
                request,
                HolidayForm(),
                success_message=f"Holiday “{form.cleaned_data['name']}” created.",
            )
            set_hx_trigger(
                response,
                event="holidayCreated",
                toast=f"Holiday “{form.cleaned_data['name']}” created.",
            )
            return response

        return _render_holiday_form(request, form)

    form = HolidayForm()
    if is_htmx_partial(request):
        return _render_holiday_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="holiday_list",
        form_url=reverse("holiday_add"),
        title="Add holiday",
    )


@login_required
@require_permission(PermissionCodename.LEAVE_HOLIDAYS_MANAGE)
@require_http_methods(["GET", "POST"])
def holiday_edit(request: HttpRequest, holiday_id: int) -> HttpResponse:
    holiday = get_object_or_404(Holiday, pk=holiday_id)

    if request.method == "POST":
        form = HolidayForm(request.POST, instance=holiday)
        if form.is_valid():
            holiday_update(**form.cleaned_data, holiday=holiday)
            response = _render_holiday_edit_form(
                request, HolidayForm(instance=holiday), holiday=holiday
            )
            response["HX-Trigger"] = "holidayUpdated"
            return response

        return _render_holiday_edit_form(request, form, holiday=holiday)

    form = HolidayForm(instance=holiday)
    if is_htmx_partial(request):
        return _render_holiday_edit_form(request, form, holiday=holiday)

    return redirect_to_list_drawer(
        list_url_name="holiday_list",
        form_url=request.path,
        title="Edit holiday",
    )


@login_required
@require_permission(PermissionCodename.LEAVE_DELETE)
@require_http_methods(["DELETE"])
def holiday_delete_view(request: HttpRequest, holiday_id: int) -> HttpResponse:
    holiday = get_object_or_404(Holiday, pk=holiday_id)
    holiday_delete(holiday=holiday)
    response = HttpResponse("")
    response["HX-Trigger"] = "holidayDeleted"
    return response
