from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from common.http import is_htmx_partial
from common.pagination import list_pagination_context
from employees.decorators import require_permission
from employees.permission_catalog import PermissionCodename
from schedule.forms import (
    ScheduleAssignmentForm,
    ShiftForm,
    TemporaryScheduleForm,
    TimetableForm,
    build_shift_day_formset,
)
from schedule.selectors import (
    schedule_assignment_list,
    shift_list,
    temporary_schedule_list,
    timetable_list,
)
from schedule.services import (
    schedule_assignment_create,
    shift_create,
    temporary_schedule_create,
    timetable_create,
)


def _render_timetable_form(
    request: HttpRequest, form: TimetableForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "schedule/timetable_add.html#timetable_form",
        {"form": form, "success_message": success_message},
    )


def _render_shift_form(
    request: HttpRequest,
    form: ShiftForm,
    formset,
    *,
    success_message: str = "",
) -> HttpResponse:
    return render(
        request,
        "schedule/shift_add.html#shift_form",
        {"form": form, "formset": formset, "success_message": success_message},
    )


def _render_assignment_form(
    request: HttpRequest,
    form: ScheduleAssignmentForm,
    *,
    success_message: str = "",
) -> HttpResponse:
    return render(
        request,
        "schedule/assignment_add.html#assignment_form",
        {"form": form, "success_message": success_message},
    )


def _render_temporary_form(
    request: HttpRequest,
    form: TemporaryScheduleForm,
    *,
    success_message: str = "",
) -> HttpResponse:
    return render(
        request,
        "schedule/temporary_add.html#temporary_form",
        {"form": form, "success_message": success_message},
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_VIEW)
@require_http_methods(["GET"])
def timetable_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        timetable_list(search=search),
        search=search,
        base_url=reverse("timetable_list"),
        hx_target="#timetable-list",
    )

    if is_htmx_partial(request):
        return render(request, "schedule/timetable_list.html#timetable_table", context)

    return render(request, "schedule/timetable_list.html", context)


@login_required
@require_permission(PermissionCodename.SCHEDULE_ADD)
@require_http_methods(["GET", "POST"])
def timetable_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = TimetableForm(request.POST)
        if form.is_valid():
            timetable_create(**form.cleaned_data)
            response = _render_timetable_form(
                request,
                TimetableForm(),
                success_message=f"Timetable “{form.cleaned_data['name']}” created.",
            )
            response["HX-Trigger"] = "timetableCreated"
            return response

        return _render_timetable_form(request, form)

    form = TimetableForm()
    if is_htmx_partial(request):
        return _render_timetable_form(request, form)

    return render(request, "schedule/timetable_add.html", {"form": form})


@login_required
@require_permission(PermissionCodename.SCHEDULE_VIEW)
@require_http_methods(["GET"])
def shift_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        shift_list(search=search),
        search=search,
        base_url=reverse("shift_list"),
        hx_target="#shift-list",
    )

    if is_htmx_partial(request):
        return render(request, "schedule/shift_list.html#shift_table", context)

    return render(request, "schedule/shift_list.html", context)


@login_required
@require_permission(PermissionCodename.SCHEDULE_ADD)
@require_http_methods(["GET", "POST"])
def shift_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ShiftForm(request.POST)
        formset = build_shift_day_formset(request.POST)
        if form.is_valid() and formset.is_valid():
            shift_days = [
                {
                    "day_number": day_form.cleaned_data["day_number"],
                    "timetable": day_form.cleaned_data["timetable"],
                }
                for day_form in formset
                if day_form.cleaned_data and not day_form.cleaned_data.get("DELETE")
            ]
            shift_create(**form.cleaned_data, shift_days=shift_days)
            response = _render_shift_form(
                request,
                ShiftForm(),
                build_shift_day_formset(),
                success_message=f"Shift “{form.cleaned_data['name']}” created.",
            )
            response["HX-Trigger"] = "shiftCreated"
            return response

        return _render_shift_form(request, form, formset)

    form = ShiftForm()
    formset = build_shift_day_formset()
    if is_htmx_partial(request):
        return _render_shift_form(request, form, formset)

    return render(
        request,
        "schedule/shift_add.html",
        {"form": form, "formset": formset},
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_VIEW)
@require_http_methods(["GET"])
def assignment_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        schedule_assignment_list(search=search),
        search=search,
        base_url=reverse("assignment_list"),
        hx_target="#assignment-list",
    )

    if is_htmx_partial(request):
        return render(
            request, "schedule/assignment_list.html#assignment_table", context
        )

    return render(request, "schedule/assignment_list.html", context)


@login_required
@require_permission(PermissionCodename.SCHEDULE_ADD)
@require_http_methods(["GET", "POST"])
def assignment_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ScheduleAssignmentForm(request.POST)
        if form.is_valid():
            schedule_assignment_create(**form.cleaned_data)
            response = _render_assignment_form(
                request,
                ScheduleAssignmentForm(),
                success_message="Schedule assignment created.",
            )
            response["HX-Trigger"] = "assignmentCreated"
            return response

        return _render_assignment_form(request, form)

    form = ScheduleAssignmentForm()
    if is_htmx_partial(request):
        return _render_assignment_form(request, form)

    return render(request, "schedule/assignment_add.html", {"form": form})


@login_required
@require_permission(PermissionCodename.SCHEDULE_VIEW)
@require_http_methods(["GET"])
def temporary_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        temporary_schedule_list(search=search),
        search=search,
        base_url=reverse("temporary_list"),
        hx_target="#temporary-list",
    )

    if is_htmx_partial(request):
        return render(request, "schedule/temporary_list.html#temporary_table", context)

    return render(request, "schedule/temporary_list.html", context)


@login_required
@require_permission(PermissionCodename.SCHEDULE_ADD)
@require_http_methods(["GET", "POST"])
def temporary_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = TemporaryScheduleForm(request.POST)
        if form.is_valid():
            temporary_schedule_create(**form.cleaned_data)
            response = _render_temporary_form(
                request,
                TemporaryScheduleForm(),
                success_message="Temporary schedule created.",
            )
            response["HX-Trigger"] = "temporaryCreated"
            return response

        return _render_temporary_form(request, form)

    form = TemporaryScheduleForm()
    if is_htmx_partial(request):
        return _render_temporary_form(request, form)

    return render(request, "schedule/temporary_add.html", {"form": form})
