from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from attendance.forms import (
    AttendanceCorrectionForm,
    AttendanceRuleForm,
    AttendanceTransactionForm,
    DailyAttendanceForm,
)
from attendance.selectors import (
    attendance_correction_list,
    attendance_rule_list,
    attendance_transaction_list,
    daily_attendance_list,
)
from attendance.services import (
    attendance_correction_create,
    attendance_rule_create,
    attendance_transaction_create,
    daily_attendance_create,
)
from common.pagination import list_pagination_context


def _configure_datetime_fields(form):
    datetime_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
    for field_name in ("timestamp", "check_in", "check_out"):
        if field_name in form.fields:
            form.fields[field_name].input_formats = datetime_formats


def _render_transaction_form(
    request: HttpRequest, form: AttendanceTransactionForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "attendance/partials/transaction_form.html",
        {"form": form, "success_message": success_message},
    )


def _render_daily_form(
    request: HttpRequest, form: DailyAttendanceForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "attendance/partials/daily_form.html",
        {"form": form, "success_message": success_message},
    )


def _render_correction_form(
    request: HttpRequest, form: AttendanceCorrectionForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "attendance/partials/correction_form.html",
        {"form": form, "success_message": success_message},
    )


def _render_rule_form(
    request: HttpRequest, form: AttendanceRuleForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "attendance/partials/rule_form.html",
        {"form": form, "success_message": success_message},
    )


@login_required
@require_http_methods(["GET"])
def transaction_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        attendance_transaction_list(search=search),
        search=search,
        base_url=reverse("attendance_transaction_list"),
        hx_target="#transaction-list",
    )

    if request.headers.get("HX-Request"):
        return render(request, "attendance/partials/transaction_table.html", context)

    return render(request, "attendance/transaction_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def transaction_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = AttendanceTransactionForm(request.POST)
        _configure_datetime_fields(form)
        if form.is_valid():
            attendance_transaction_create(**form.cleaned_data)
            form = AttendanceTransactionForm()
            _configure_datetime_fields(form)
            response = _render_transaction_form(
                request,
                form,
                success_message="Attendance transaction recorded.",
            )
            response["HX-Trigger"] = "attendanceTransactionCreated"
            return response

        return _render_transaction_form(request, form)

    form = AttendanceTransactionForm()
    _configure_datetime_fields(form)
    if request.headers.get("HX-Request"):
        return _render_transaction_form(request, form)

    return render(request, "attendance/transaction_add.html", {"form": form})


@login_required
@require_http_methods(["GET"])
def daily_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        daily_attendance_list(search=search),
        search=search,
        base_url=reverse("daily_attendance_list"),
        hx_target="#daily-list",
    )

    if request.headers.get("HX-Request"):
        return render(request, "attendance/partials/daily_table.html", context)

    return render(request, "attendance/daily_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def daily_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = DailyAttendanceForm(request.POST)
        if form.is_valid():
            daily_attendance_create(**form.cleaned_data)
            response = _render_daily_form(
                request,
                DailyAttendanceForm(),
                success_message="Daily attendance record created.",
            )
            response["HX-Trigger"] = "dailyAttendanceCreated"
            return response

        return _render_daily_form(request, form)

    form = DailyAttendanceForm()
    if request.headers.get("HX-Request"):
        return _render_daily_form(request, form)

    return render(request, "attendance/daily_add.html", {"form": form})


@login_required
@require_http_methods(["GET"])
def correction_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        attendance_correction_list(search=search),
        search=search,
        base_url=reverse("attendance_correction_list"),
        hx_target="#correction-list",
    )

    if request.headers.get("HX-Request"):
        return render(request, "attendance/partials/correction_table.html", context)

    return render(request, "attendance/correction_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def correction_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = AttendanceCorrectionForm(request.POST)
        _configure_datetime_fields(form)
        if form.is_valid():
            attendance_correction_create(
                **form.cleaned_data,
                requested_by=request.user,
            )
            form = AttendanceCorrectionForm()
            _configure_datetime_fields(form)
            response = _render_correction_form(
                request,
                form,
                success_message="Attendance correction submitted.",
            )
            response["HX-Trigger"] = "attendanceCorrectionCreated"
            return response

        return _render_correction_form(request, form)

    form = AttendanceCorrectionForm()
    _configure_datetime_fields(form)
    if request.headers.get("HX-Request"):
        return _render_correction_form(request, form)

    return render(request, "attendance/correction_add.html", {"form": form})


@login_required
@require_http_methods(["GET"])
def rule_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        attendance_rule_list(search=search),
        search=search,
        base_url=reverse("attendance_rule_list"),
        hx_target="#rule-list",
    )

    if request.headers.get("HX-Request"):
        return render(request, "attendance/partials/rule_table.html", context)

    return render(request, "attendance/rule_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def rule_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = AttendanceRuleForm(request.POST)
        if form.is_valid():
            attendance_rule_create(**form.cleaned_data)
            response = _render_rule_form(
                request,
                AttendanceRuleForm(),
                success_message=f"Rule “{form.cleaned_data['name']}” created.",
            )
            response["HX-Trigger"] = "attendanceRuleCreated"
            return response

        return _render_rule_form(request, form)

    form = AttendanceRuleForm()
    if request.headers.get("HX-Request"):
        return _render_rule_form(request, form)

    return render(request, "attendance/rule_add.html", {"form": form})
