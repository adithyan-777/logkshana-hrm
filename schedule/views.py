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
from schedule.forms import (
    ScheduleForm,
    TimetableForm,
    build_timetable_break_formset,
)
from schedule.models import Schedule, Timetable
from schedule.selectors import schedule_list, timetable_list
from schedule.services import (
    schedule_create,
    schedule_delete,
    schedule_update,
    timetable_create,
    timetable_delete,
    timetable_update,
)


def _render_timetable_form(
    request: HttpRequest, form: TimetableForm, formset, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "schedule/timetable_add.html#timetable_form",
        {"form": form, "formset": formset, "success_message": success_message},
    )


def _render_timetable_edit_form(
    request: HttpRequest, form: TimetableForm, formset, *, timetable: Timetable
) -> HttpResponse:
    return render(
        request,
        "schedule/timetable_edit.html#timetable_edit_form",
        {"form": form, "formset": formset, "timetable": timetable},
    )


def _render_schedule_form(
    request: HttpRequest, form: ScheduleForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "schedule/schedule_add.html#schedule_form",
        {"form": form, "success_message": success_message},
    )


def _render_schedule_edit_form(
    request: HttpRequest, form: ScheduleForm, *, schedule: Schedule
) -> HttpResponse:
    return render(
        request,
        "schedule/schedule_edit.html#schedule_edit_form",
        {"form": form, "schedule": schedule},
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
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.SCHEDULE_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.SCHEDULE_DELETE
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
        formset = build_timetable_break_formset(request.POST)
        if form.is_valid() and formset.is_valid():
            timetable = timetable_create(**form.cleaned_data)
            formset.instance = timetable
            formset.save()
            response = _render_timetable_form(
                request,
                TimetableForm(),
                build_timetable_break_formset(),
                success_message=f"Timetable “{form.cleaned_data['name']}” created.",
            )
            set_hx_trigger(
                response,
                event="timetableCreated",
                toast=f"Timetable “{form.cleaned_data['name']}” created.",
            )
            return response

        return _render_timetable_form(request, form, formset)

    form = TimetableForm()
    formset = build_timetable_break_formset()
    if is_htmx_partial(request):
        return _render_timetable_form(request, form, formset)

    return redirect_to_list_drawer(
        list_url_name="timetable_list",
        form_url=reverse("timetable_add"),
        title="Add timetable",
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_ADD)
@require_http_methods(["GET", "POST"])
def timetable_edit(request: HttpRequest, timetable_id: int) -> HttpResponse:
    timetable = get_object_or_404(Timetable, pk=timetable_id)

    if request.method == "POST":
        form = TimetableForm(request.POST, instance=timetable)
        formset = build_timetable_break_formset(request.POST, instance=timetable)
        if form.is_valid() and formset.is_valid():
            timetable_update(**form.cleaned_data, timetable=timetable)
            formset.save()
            response = _render_timetable_edit_form(
                request,
                TimetableForm(instance=timetable),
                build_timetable_break_formset(instance=timetable),
                timetable=timetable,
            )
            set_hx_trigger(
                response,
                event="timetableUpdated",
                toast=f"Timetable “{timetable.name}” updated.",
            )
            return response

        return _render_timetable_edit_form(request, form, formset, timetable=timetable)

    form = TimetableForm(instance=timetable)
    formset = build_timetable_break_formset(instance=timetable)
    if is_htmx_partial(request):
        return _render_timetable_edit_form(request, form, formset, timetable=timetable)

    return redirect_to_list_drawer(
        list_url_name="timetable_list",
        form_url=request.path,
        title="Edit timetable",
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_DELETE)
@require_http_methods(["DELETE"])
def timetable_delete_view(request: HttpRequest, timetable_id: int) -> HttpResponse:
    timetable = get_object_or_404(Timetable, pk=timetable_id)
    timetable_delete(timetable=timetable)
    response = HttpResponse("")
    response["HX-Trigger"] = "timetableDeleted"
    return response


@login_required
@require_permission(PermissionCodename.SCHEDULE_VIEW)
@require_http_methods(["GET"])
def schedule_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        schedule_list(search=search),
        search=search,
        base_url=reverse("schedule_list"),
        hx_target="#schedule-list",
    )
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.SCHEDULE_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.SCHEDULE_DELETE
    )

    if is_htmx_partial(request):
        return render(request, "schedule/schedule_list.html#schedule_table", context)

    return render(request, "schedule/schedule_list.html", context)


@login_required
@require_permission(PermissionCodename.SCHEDULE_ADD)
@require_http_methods(["GET", "POST"])
def schedule_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ScheduleForm(request.POST)
        if form.is_valid():
            schedule_create(**form.cleaned_data)
            response = _render_schedule_form(
                request,
                ScheduleForm(),
                success_message=f"Schedule “{form.cleaned_data['name']}” created.",
            )
            set_hx_trigger(
                response,
                event="scheduleCreated",
                toast=f"Schedule “{form.cleaned_data['name']}” created.",
            )
            return response

        return _render_schedule_form(request, form)

    form = ScheduleForm()
    if is_htmx_partial(request):
        return _render_schedule_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="schedule_list",
        form_url=reverse("schedule_add"),
        title="Add schedule",
        size="wide",
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_ADD)
@require_http_methods(["GET", "POST"])
def schedule_edit(request: HttpRequest, schedule_id: int) -> HttpResponse:
    schedule = get_object_or_404(Schedule, pk=schedule_id)

    if request.method == "POST":
        form = ScheduleForm(request.POST, instance=schedule)
        if form.is_valid():
            schedule_update(**form.cleaned_data, schedule=schedule)
            response = _render_schedule_edit_form(
                request, ScheduleForm(instance=schedule), schedule=schedule
            )
            set_hx_trigger(
                response,
                event="scheduleUpdated",
                toast=f"Schedule “{schedule.name}” updated.",
            )
            return response

        return _render_schedule_edit_form(request, form, schedule=schedule)

    form = ScheduleForm(instance=schedule)
    if is_htmx_partial(request):
        return _render_schedule_edit_form(request, form, schedule=schedule)

    return redirect_to_list_drawer(
        list_url_name="schedule_list",
        form_url=request.path,
        title="Edit schedule",
        size="wide",
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_DELETE)
@require_http_methods(["DELETE"])
def schedule_delete_view(request: HttpRequest, schedule_id: int) -> HttpResponse:
    schedule = get_object_or_404(Schedule, pk=schedule_id)
    schedule_delete(schedule=schedule)
    response = HttpResponse("")
    response["HX-Trigger"] = "scheduleDeleted"
    return response
