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
    ScheduleAssignmentForm,
    ShiftForm,
    TemporaryScheduleForm,
    TimetableForm,
    build_shift_day_formset,
)
from schedule.models import (
    ScheduleAssignment,
    Shift,
    TemporarySchedule,
    Timetable,
)
from schedule.selectors import (
    schedule_assignment_list,
    shift_list,
    temporary_schedule_list,
    timetable_list,
)
from schedule.services import (
    schedule_assignment_create,
    schedule_assignment_delete,
    schedule_assignment_update,
    shift_create,
    shift_delete,
    shift_update,
    temporary_schedule_create,
    temporary_schedule_delete,
    temporary_schedule_update,
    timetable_create,
    timetable_delete,
    timetable_update,
)


def _render_timetable_form(
    request: HttpRequest, form: TimetableForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "schedule/timetable_add.html#timetable_form",
        {"form": form, "success_message": success_message},
    )


def _render_timetable_edit_form(
    request: HttpRequest, form: TimetableForm, *, timetable: Timetable
) -> HttpResponse:
    return render(
        request,
        "schedule/timetable_edit.html#timetable_edit_form",
        {"form": form, "timetable": timetable},
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


def _render_shift_edit_form(
    request: HttpRequest,
    form: ShiftForm,
    formset,
    *,
    shift: Shift,
) -> HttpResponse:
    return render(
        request,
        "schedule/shift_edit.html#shift_edit_form",
        {"form": form, "formset": formset, "shift": shift},
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


def _render_assignment_edit_form(
    request: HttpRequest,
    form: ScheduleAssignmentForm,
    *,
    assignment: ScheduleAssignment,
) -> HttpResponse:
    return render(
        request,
        "schedule/assignment_edit.html#assignment_edit_form",
        {"form": form, "assignment": assignment},
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


def _render_temporary_edit_form(
    request: HttpRequest,
    form: TemporaryScheduleForm,
    *,
    temporary: TemporarySchedule,
) -> HttpResponse:
    return render(
        request,
        "schedule/temporary_edit.html#temporary_edit_form",
        {"form": form, "temporary": temporary},
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
        if form.is_valid():
            payload = form.service_kwargs()
            timetable_create(**payload)
            response = _render_timetable_form(
                request,
                TimetableForm(),
                success_message=f"Timetable “{payload['name']}” created.",
            )
            set_hx_trigger(
                response,
                event="timetableCreated",
                toast=f"Timetable “{payload['name']}” created.",
            )
            return response

        return _render_timetable_form(request, form)

    form = TimetableForm()
    if is_htmx_partial(request):
        return _render_timetable_form(request, form)

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
        if form.is_valid():
            payload = form.service_kwargs()
            timetable_update(**payload, timetable=timetable)
            response = _render_timetable_edit_form(
                request, TimetableForm(instance=timetable), timetable=timetable
            )
            set_hx_trigger(
                response,
                event="timetableUpdated",
                toast=f"Timetable “{timetable.name}” updated.",
            )
            return response

        return _render_timetable_edit_form(request, form, timetable=timetable)

    form = TimetableForm(instance=timetable)
    if is_htmx_partial(request):
        return _render_timetable_edit_form(request, form, timetable=timetable)

    return redirect_to_list_drawer(
        list_url_name="timetable_list",
        form_url=reverse("timetable_edit", args=[timetable.pk]),
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
def shift_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        shift_list(search=search),
        search=search,
        base_url=reverse("shift_list"),
        hx_target="#shift-list",
    )
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.SCHEDULE_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.SCHEDULE_DELETE
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
            set_hx_trigger(
                response,
                event="shiftCreated",
                toast=f"Shift “{form.cleaned_data['name']}” created.",
            )
            return response

        return _render_shift_form(request, form, formset)

    form = ShiftForm()
    formset = build_shift_day_formset()
    if is_htmx_partial(request):
        return _render_shift_form(request, form, formset)

    return redirect_to_list_drawer(
        list_url_name="shift_list",
        form_url=reverse("shift_add"),
        title="Add shift",
        size="wide",
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_ADD)
@require_http_methods(["GET", "POST"])
def shift_edit(request: HttpRequest, shift_id: int) -> HttpResponse:
    shift = get_object_or_404(Shift, pk=shift_id)

    if request.method == "POST":
        form = ShiftForm(request.POST, instance=shift)
        formset = build_shift_day_formset(request.POST, instance=shift)
        if form.is_valid() and formset.is_valid():
            shift_days = [
                {
                    "day_number": day_form.cleaned_data["day_number"],
                    "timetable": day_form.cleaned_data["timetable"],
                }
                for day_form in formset
                if day_form.cleaned_data and not day_form.cleaned_data.get("DELETE")
            ]
            shift_update(**form.cleaned_data, shift=shift, shift_days=shift_days)
            response = _render_shift_edit_form(
                request,
                ShiftForm(instance=shift),
                build_shift_day_formset(instance=shift),
                shift=shift,
            )
            response["HX-Trigger"] = "shiftUpdated"
            return response

        return _render_shift_edit_form(request, form, formset, shift=shift)

    form = ShiftForm(instance=shift)
    formset = build_shift_day_formset(instance=shift)
    if is_htmx_partial(request):
        return _render_shift_edit_form(request, form, formset, shift=shift)

    return redirect_to_list_drawer(
        list_url_name="shift_list",
        form_url=reverse("shift_edit", args=[shift.pk]),
        title="Edit shift",
        size="wide",
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_DELETE)
@require_http_methods(["DELETE"])
def shift_delete_view(request: HttpRequest, shift_id: int) -> HttpResponse:
    shift = get_object_or_404(Shift, pk=shift_id)
    shift_delete(shift=shift)
    response = HttpResponse("")
    response["HX-Trigger"] = "shiftDeleted"
    return response


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
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.SCHEDULE_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.SCHEDULE_DELETE
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
            set_hx_trigger(
                response,
                event="assignmentCreated",
                toast="Schedule assignment created.",
            )
            return response

        return _render_assignment_form(request, form)

    form = ScheduleAssignmentForm()
    if is_htmx_partial(request):
        return _render_assignment_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="assignment_list",
        form_url=reverse("assignment_add"),
        title="Add assignment",
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_ADD)
@require_http_methods(["GET", "POST"])
def assignment_edit(request: HttpRequest, assignment_id: int) -> HttpResponse:
    assignment = get_object_or_404(ScheduleAssignment, pk=assignment_id)

    if request.method == "POST":
        form = ScheduleAssignmentForm(request.POST, instance=assignment)
        if form.is_valid():
            schedule_assignment_update(**form.cleaned_data, assignment=assignment)
            response = _render_assignment_edit_form(
                request,
                ScheduleAssignmentForm(instance=assignment),
                assignment=assignment,
            )
            response["HX-Trigger"] = "assignmentUpdated"
            return response

        return _render_assignment_edit_form(request, form, assignment=assignment)

    form = ScheduleAssignmentForm(instance=assignment)
    if is_htmx_partial(request):
        return _render_assignment_edit_form(request, form, assignment=assignment)

    return redirect_to_list_drawer(
        list_url_name="assignment_list",
        form_url=reverse("assignment_edit", args=[assignment.pk]),
        title="Edit assignment",
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_DELETE)
@require_http_methods(["DELETE"])
def assignment_delete_view(request: HttpRequest, assignment_id: int) -> HttpResponse:
    assignment = get_object_or_404(ScheduleAssignment, pk=assignment_id)
    schedule_assignment_delete(assignment=assignment)
    response = HttpResponse("")
    response["HX-Trigger"] = "assignmentDeleted"
    return response


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
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.SCHEDULE_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.SCHEDULE_DELETE
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
            set_hx_trigger(
                response,
                event="temporaryCreated",
                toast="Temporary schedule created.",
            )
            return response

        return _render_temporary_form(request, form)

    form = TemporaryScheduleForm()
    if is_htmx_partial(request):
        return _render_temporary_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="temporary_list",
        form_url=reverse("temporary_add"),
        title="Add temporary schedule",
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_ADD)
@require_http_methods(["GET", "POST"])
def temporary_edit(request: HttpRequest, temporary_id: int) -> HttpResponse:
    temporary = get_object_or_404(TemporarySchedule, pk=temporary_id)

    if request.method == "POST":
        form = TemporaryScheduleForm(request.POST, instance=temporary)
        if form.is_valid():
            temporary_schedule_update(**form.cleaned_data, temporary=temporary)
            response = _render_temporary_edit_form(
                request,
                TemporaryScheduleForm(instance=temporary),
                temporary=temporary,
            )
            response["HX-Trigger"] = "temporaryUpdated"
            return response

        return _render_temporary_edit_form(request, form, temporary=temporary)

    form = TemporaryScheduleForm(instance=temporary)
    if is_htmx_partial(request):
        return _render_temporary_edit_form(request, form, temporary=temporary)

    return redirect_to_list_drawer(
        list_url_name="temporary_list",
        form_url=reverse("temporary_edit", args=[temporary.pk]),
        title="Edit temporary schedule",
    )


@login_required
@require_permission(PermissionCodename.SCHEDULE_DELETE)
@require_http_methods(["DELETE"])
def temporary_delete_view(request: HttpRequest, temporary_id: int) -> HttpResponse:
    temporary = get_object_or_404(TemporarySchedule, pk=temporary_id)
    temporary_schedule_delete(temporary=temporary)
    response = HttpResponse("")
    response["HX-Trigger"] = "temporaryDeleted"
    return response
