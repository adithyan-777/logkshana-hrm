from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from common.pagination import list_pagination_context
from leave.forms import (
    HolidayForm,
    LeavePolicyForm,
    LeaveRequestForm,
    LeaveTypeForm,
)
from leave.selectors import (
    holiday_list,
    leave_policy_list,
    leave_request_list,
    leave_type_list,
)
from leave.services import (
    holiday_create,
    leave_policy_create,
    leave_request_create,
    leave_type_create,
)


def _render_leave_type_form(
    request: HttpRequest, form: LeaveTypeForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "leave/partials/leave_type_form.html",
        {"form": form, "success_message": success_message},
    )


def _render_leave_policy_form(
    request: HttpRequest, form: LeavePolicyForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "leave/partials/leave_policy_form.html",
        {"form": form, "success_message": success_message},
    )


def _render_leave_request_form(
    request: HttpRequest, form: LeaveRequestForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "leave/partials/leave_request_form.html",
        {"form": form, "success_message": success_message},
    )


def _render_holiday_form(
    request: HttpRequest, form: HolidayForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "leave/partials/holiday_form.html",
        {"form": form, "success_message": success_message},
    )


@login_required
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

    if request.headers.get("HX-Request"):
        return render(request, "leave/partials/leave_type_table.html", context)

    return render(request, "leave/leave_type_list.html", context)


@login_required
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
            response["HX-Trigger"] = "leaveTypeCreated"
            return response

        return _render_leave_type_form(request, form)

    form = LeaveTypeForm()
    if request.headers.get("HX-Request"):
        return _render_leave_type_form(request, form)

    return render(request, "leave/leave_type_add.html", {"form": form})


@login_required
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

    if request.headers.get("HX-Request"):
        return render(request, "leave/partials/leave_policy_table.html", context)

    return render(request, "leave/leave_policy_list.html", context)


@login_required
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
            response["HX-Trigger"] = "leavePolicyCreated"
            return response

        return _render_leave_policy_form(request, form)

    form = LeavePolicyForm()
    if request.headers.get("HX-Request"):
        return _render_leave_policy_form(request, form)

    return render(request, "leave/leave_policy_add.html", {"form": form})


@login_required
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

    if request.headers.get("HX-Request"):
        return render(request, "leave/partials/leave_request_table.html", context)

    return render(request, "leave/leave_request_list.html", context)


@login_required
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
            response["HX-Trigger"] = "leaveRequestCreated"
            return response

        return _render_leave_request_form(request, form)

    form = LeaveRequestForm()
    if request.headers.get("HX-Request"):
        return _render_leave_request_form(request, form)

    return render(request, "leave/leave_request_add.html", {"form": form})


@login_required
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

    if request.headers.get("HX-Request"):
        return render(request, "leave/partials/holiday_table.html", context)

    return render(request, "leave/holiday_list.html", context)


@login_required
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
            response["HX-Trigger"] = "holidayCreated"
            return response

        return _render_holiday_form(request, form)

    form = HolidayForm()
    if request.headers.get("HX-Request"):
        return _render_holiday_form(request, form)

    return render(request, "leave/holiday_add.html", {"form": form})
