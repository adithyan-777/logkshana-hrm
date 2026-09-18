import json
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from attendance.forms import (
    AttendanceCorrectionForm,
    AttendanceRuleForm,
    AttendanceTransactionForm,
    DailyAttendanceForm,
)
from attendance.integrations.gateway import gateway_request_is_authorized
from attendance.models import (
    AttendanceCorrection,
    AttendanceRule,
    AttendanceTransaction,
    DailyAttendance,
)
from attendance.selectors import (
    attendance_correction_list,
    attendance_rule_list,
    attendance_transaction_list,
    daily_attendance_list,
)
from attendance.services import (
    attendance_correction_create,
    attendance_correction_delete,
    attendance_correction_update,
    attendance_rule_create,
    attendance_rule_delete,
    attendance_rule_update,
    attendance_transaction_create,
    attendance_transaction_delete,
    attendance_transaction_update,
    daily_attendance_create,
    daily_attendance_delete,
    daily_attendance_update,
)
from common.http import is_htmx_partial
from common.pagination import list_pagination_context
from employees.decorators import require_permission
from employees.permission_catalog import PermissionCodename
from employees.selectors import employee_get_for_user, user_has_permission


def verify_gateway_secret_key(request: HttpRequest) -> bool:
    """Return True when the request carries valid gateway credentials.

    Accepts ``Authorization: Bearer <GATEWAY_SECRET_KEY>`` (canonical),
    ``X-Gateway-Token`` header, or the legacy ``?secret_key=`` query param.
    """
    return gateway_request_is_authorized(request)


def require_gateway_secret(view_func):
    """View decorator enforcing gateway credentials (403 on failure)."""

    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not gateway_request_is_authorized(request):
            return JsonResponse(
                {"detail": "Invalid or missing gateway credentials."},
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return _wrapped


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
        "attendance/transaction_add.html#transaction_form",
        {"form": form, "success_message": success_message},
    )


def _render_daily_form(
    request: HttpRequest, form: DailyAttendanceForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "attendance/daily_add.html#daily_form",
        {"form": form, "success_message": success_message},
    )


def _render_correction_form(
    request: HttpRequest, form: AttendanceCorrectionForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "attendance/correction_add.html#correction_form",
        {"form": form, "success_message": success_message},
    )


def _render_rule_form(
    request: HttpRequest, form: AttendanceRuleForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "attendance/rule_add.html#rule_form",
        {"form": form, "success_message": success_message},
    )


@login_required
@require_permission(PermissionCodename.ATTENDANCE_VIEW)
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
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.ATTENDANCE_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.ATTENDANCE_DELETE
    )

    if is_htmx_partial(request):
        return render(
            request, "attendance/transaction_list.html#transaction_table", context
        )

    return render(request, "attendance/transaction_list.html", context)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_ADD)
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
    if is_htmx_partial(request):
        return _render_transaction_form(request, form)

    return render(request, "attendance/transaction_add.html", {"form": form})


def _render_transaction_edit_form(
    request: HttpRequest, form: AttendanceTransactionForm, *, transaction
) -> HttpResponse:
    return render(
        request,
        "attendance/transaction_edit.html#transaction_edit_form",
        {"form": form, "transaction": transaction},
    )


@login_required
@require_permission(PermissionCodename.ATTENDANCE_ADD)
@require_http_methods(["GET", "POST"])
def transaction_edit(request: HttpRequest, transaction_id: int) -> HttpResponse:
    transaction = get_object_or_404(AttendanceTransaction, pk=transaction_id)

    if request.method == "POST":
        form = AttendanceTransactionForm(request.POST, instance=transaction)
        _configure_datetime_fields(form)
        if form.is_valid():
            attendance_transaction_update(
                **form.cleaned_data, transaction=transaction
            )
            response = _render_transaction_edit_form(
                request,
                AttendanceTransactionForm(instance=transaction),
                transaction=transaction,
            )
            response["HX-Trigger"] = "transactionUpdated"
            return response

        return _render_transaction_edit_form(request, form, transaction=transaction)

    form = AttendanceTransactionForm(instance=transaction)
    _configure_datetime_fields(form)
    if is_htmx_partial(request):
        return _render_transaction_edit_form(request, form, transaction=transaction)

    return render(
        request,
        "attendance/transaction_edit.html",
        {"form": form, "transaction": transaction},
    )


def attendance_transaction_edit(
    request: HttpRequest, attendance_transaction_id: int
) -> HttpResponse:
    return transaction_edit(request, transaction_id=attendance_transaction_id)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_DELETE)
@require_http_methods(["DELETE"])
def transaction_delete_view(request: HttpRequest, transaction_id: int) -> HttpResponse:
    transaction = get_object_or_404(AttendanceTransaction, pk=transaction_id)
    attendance_transaction_delete(transaction=transaction)
    response = HttpResponse("")
    response["HX-Trigger"] = "transactionDeleted"
    return response


def attendance_transaction_delete_view(
    request: HttpRequest, attendance_transaction_id: int
) -> HttpResponse:
    return transaction_delete_view(
        request, transaction_id=attendance_transaction_id
    )


@login_required
@require_permission(PermissionCodename.ATTENDANCE_VIEW)
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
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.ATTENDANCE_ADD
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.ATTENDANCE_DELETE
    )

    if is_htmx_partial(request):
        return render(request, "attendance/daily_list.html#daily_table", context)

    return render(request, "attendance/daily_list.html", context)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_ADD)
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
    if is_htmx_partial(request):
        return _render_daily_form(request, form)

    return render(request, "attendance/daily_add.html", {"form": form})


def _render_daily_edit_form(
    request: HttpRequest, form: DailyAttendanceForm, *, daily_attendance
) -> HttpResponse:
    return render(
        request,
        "attendance/daily_edit.html#daily_edit_form",
        {"form": form, "daily_attendance": daily_attendance},
    )


@login_required
@require_permission(PermissionCodename.ATTENDANCE_ADD)
@require_http_methods(["GET", "POST"])
def daily_edit(request: HttpRequest, daily_id: int) -> HttpResponse:
    daily_attendance = get_object_or_404(DailyAttendance, pk=daily_id)

    if request.method == "POST":
        form = DailyAttendanceForm(request.POST, instance=daily_attendance)
        if form.is_valid():
            daily_attendance_update(
                **form.cleaned_data, daily_attendance=daily_attendance
            )
            response = _render_daily_edit_form(
                request,
                DailyAttendanceForm(instance=daily_attendance),
                daily_attendance=daily_attendance,
            )
            response["HX-Trigger"] = "dailyUpdated"
            return response

        return _render_daily_edit_form(
            request, form, daily_attendance=daily_attendance
        )

    form = DailyAttendanceForm(instance=daily_attendance)
    if is_htmx_partial(request):
        return _render_daily_edit_form(
            request, form, daily_attendance=daily_attendance
        )

    return render(
        request,
        "attendance/daily_edit.html",
        {"form": form, "daily_attendance": daily_attendance},
    )


def daily_attendance_edit(
    request: HttpRequest, daily_attendance_id: int
) -> HttpResponse:
    return daily_edit(request, daily_id=daily_attendance_id)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_DELETE)
@require_http_methods(["DELETE"])
def daily_delete_view(request: HttpRequest, daily_id: int) -> HttpResponse:
    daily_attendance = get_object_or_404(DailyAttendance, pk=daily_id)
    daily_attendance_delete(daily_attendance=daily_attendance)
    response = HttpResponse("")
    response["HX-Trigger"] = "dailyDeleted"
    return response


def daily_attendance_delete_view(
    request: HttpRequest, daily_attendance_id: int
) -> HttpResponse:
    return daily_delete_view(request, daily_id=daily_attendance_id)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_CORRECT)
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
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.ATTENDANCE_CORRECT
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.ATTENDANCE_DELETE
    )

    if is_htmx_partial(request):
        return render(
            request, "attendance/correction_list.html#correction_table", context
        )

    return render(request, "attendance/correction_list.html", context)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_CORRECT)
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
    if is_htmx_partial(request):
        return _render_correction_form(request, form)

    return render(request, "attendance/correction_add.html", {"form": form})


def _render_correction_edit_form(
    request: HttpRequest, form: AttendanceCorrectionForm, *, correction
) -> HttpResponse:
    return render(
        request,
        "attendance/correction_edit.html#correction_edit_form",
        {"form": form, "correction": correction},
    )


@login_required
@require_permission(PermissionCodename.ATTENDANCE_CORRECT)
@require_http_methods(["GET", "POST"])
def correction_edit(request: HttpRequest, correction_id: int) -> HttpResponse:
    correction = get_object_or_404(AttendanceCorrection, pk=correction_id)

    if request.method == "POST":
        form = AttendanceCorrectionForm(request.POST, instance=correction)
        _configure_datetime_fields(form)
        if form.is_valid():
            attendance_correction_update(
                **form.cleaned_data,
                correction=correction,
                requested_by=correction.requested_by,
            )
            response = _render_correction_edit_form(
                request,
                AttendanceCorrectionForm(instance=correction),
                correction=correction,
            )
            response["HX-Trigger"] = "correctionUpdated"
            return response

        return _render_correction_edit_form(request, form, correction=correction)

    form = AttendanceCorrectionForm(instance=correction)
    _configure_datetime_fields(form)
    if is_htmx_partial(request):
        return _render_correction_edit_form(request, form, correction=correction)

    return render(
        request,
        "attendance/correction_edit.html",
        {"form": form, "correction": correction},
    )


def attendance_correction_edit(
    request: HttpRequest, attendance_correction_id: int
) -> HttpResponse:
    return correction_edit(request, correction_id=attendance_correction_id)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_DELETE)
@require_http_methods(["DELETE"])
def correction_delete_view(request: HttpRequest, correction_id: int) -> HttpResponse:
    correction = get_object_or_404(AttendanceCorrection, pk=correction_id)
    attendance_correction_delete(correction=correction)
    response = HttpResponse("")
    response["HX-Trigger"] = "correctionDeleted"
    return response


def attendance_correction_delete_view(
    request: HttpRequest, attendance_correction_id: int
) -> HttpResponse:
    return correction_delete_view(request, correction_id=attendance_correction_id)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_RULES_MANAGE)
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
    context["can_edit"] = user_has_permission(
        user=request.user, codename=PermissionCodename.ATTENDANCE_RULES_MANAGE
    )
    context["can_delete"] = user_has_permission(
        user=request.user, codename=PermissionCodename.ATTENDANCE_DELETE
    )

    if is_htmx_partial(request):
        return render(request, "attendance/rule_list.html#rule_table", context)

    return render(request, "attendance/rule_list.html", context)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_RULES_MANAGE)
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
    if is_htmx_partial(request):
        return _render_rule_form(request, form)

    return render(request, "attendance/rule_add.html", {"form": form})


def _render_rule_edit_form(
    request: HttpRequest, form: AttendanceRuleForm, *, rule
) -> HttpResponse:
    return render(
        request,
        "attendance/rule_edit.html#rule_edit_form",
        {"form": form, "rule": rule},
    )


@login_required
@require_permission(PermissionCodename.ATTENDANCE_RULES_MANAGE)
@require_http_methods(["GET", "POST"])
def rule_edit(request: HttpRequest, rule_id: int) -> HttpResponse:
    rule = get_object_or_404(AttendanceRule, pk=rule_id)

    if request.method == "POST":
        form = AttendanceRuleForm(request.POST, instance=rule)
        if form.is_valid():
            attendance_rule_update(**form.cleaned_data, rule=rule)
            response = _render_rule_edit_form(
                request, AttendanceRuleForm(instance=rule), rule=rule
            )
            response["HX-Trigger"] = "ruleUpdated"
            return response

        return _render_rule_edit_form(request, form, rule=rule)

    form = AttendanceRuleForm(instance=rule)
    if is_htmx_partial(request):
        return _render_rule_edit_form(request, form, rule=rule)

    return render(
        request,
        "attendance/rule_edit.html",
        {"form": form, "rule": rule},
    )


def attendance_rule_edit(
    request: HttpRequest, attendance_rule_id: int
) -> HttpResponse:
    return rule_edit(request, rule_id=attendance_rule_id)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_DELETE)
@require_http_methods(["DELETE"])
def rule_delete_view(request: HttpRequest, rule_id: int) -> HttpResponse:
    rule = get_object_or_404(AttendanceRule, pk=rule_id)
    attendance_rule_delete(rule=rule)
    response = HttpResponse("")
    response["HX-Trigger"] = "ruleDeleted"
    return response


def attendance_rule_delete_view(
    request: HttpRequest, attendance_rule_id: int
) -> HttpResponse:
    return rule_delete_view(request, rule_id=attendance_rule_id)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_OWN_VIEW)
@require_http_methods(["GET"])
def my_attendance_view(request: HttpRequest) -> HttpResponse:
    employee = employee_get_for_user(user=request.user)
    search = request.GET.get("q", "").strip()
    if employee is None:
        queryset = DailyAttendance.objects.none()
    else:
        queryset = daily_attendance_list(search=search, employee=employee)
    context = list_pagination_context(
        request,
        queryset,
        search=search,
        base_url=reverse("my_attendance"),
        hx_target="#my-attendance-list",
    )
    context["employee"] = employee

    if is_htmx_partial(request):
        return render(
            request,
            "attendance/my_attendance.html#my_attendance_table",
            context,
        )

    return render(request, "attendance/my_attendance.html", context)

@csrf_exempt
@require_http_methods(["POST"])
@require_gateway_secret
def gateway_view(request: HttpRequest) -> HttpResponse:
    """Device-gateway push endpoint (gateway-native payload).

    Accepts a single JSON object or a list of objects shaped as the gateway
    sends them::

        {"gateway_log_id": 2, "serial_number": "ZK-001", "user_id": "1001",
         "timestamp": "2026-09-02T09:00:00Z",
         "status": 0, "verify_mode": 1, "work_code": "0"}

    ``user_id`` (gateway PIN) maps to pattika's ``employee_id``; extra
    gateway fields are preserved in the punch's ``raw_data``. Replays are
    idempotent (same ``device:<serial>:<emp>:<timestamp>`` external id).
    Each accepted punch also recalculates the employee's DailyAttendance
    for the punch's attendance day (periods, worked/late/early/overtime
    minutes, status).
    """
    from companies.services import attendance_log_create

    try:
        payload = json.loads(request.body or b"")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    is_batch = isinstance(payload, list)
    items = payload if is_batch else [payload]
    if not items or not all(isinstance(item, dict) for item in items):
        return JsonResponse(
            {"detail": "Expected a JSON object or a non-empty list of objects."},
            status=400,
        )

    results = []
    for item in items:
        results.append(_gateway_push_item(item, attendance_log_create))

    if not is_batch:
        result = results[0]
        status_code = 201 if result["ok"] else 400
        return JsonResponse(result["body"], status=status_code)

    ok_count = sum(1 for result in results if result["ok"])
    body = {
        "created": ok_count,
        "errors": len(results) - ok_count,
        "results": [result["body"] for result in results],
    }
    if ok_count == len(results):
        return JsonResponse(body, status=201)
    if ok_count == 0:
        return JsonResponse(body, status=400)
    return JsonResponse(body, status=207)


def _gateway_push_item(item: dict, attendance_log_create) -> dict:
    """Process one gateway push log. Returns {"ok": bool, "body": dict}."""
    serial_number = item.get("serial_number")
    employee_id = item.get("user_id") or item.get("employee_id")
    timestamp_raw = item.get("timestamp")

    errors = {}
    if not serial_number:
        errors["serial_number"] = "This field is required."
    if not employee_id:
        errors["user_id"] = "This field is required (or provide employee_id)."
    timestamp = parse_datetime(str(timestamp_raw)) if timestamp_raw else None
    if timestamp is None:
        errors["timestamp"] = "Enter a valid datetime."
    if errors:
        return {"ok": False, "body": {"errors": errors, "log": _gateway_log_ref(item)}}

    # Preserve every other gateway field (gateway_id, status, verify_mode,
    # work_code, ...) in raw_data, so new gateway fields are stored without
    # needing a code change.
    extra = {
        key: value
        for key, value in item.items()
        if key not in ("serial_number", "user_id", "employee_id", "timestamp")
    }
    # Gateway identifies logs with ``gateway_log_id`` (older payloads used
    # ``id``). Passing it through lets push and pull share one external id
    # (``gateway:<id>``), so a log both pushed and pulled never duplicates.
    gateway_log_id = item.get("gateway_log_id", item.get("id"))
    try:
        punch = attendance_log_create(
            serial_number=serial_number,
            employee_id=str(employee_id),
            gateway_log_id=gateway_log_id,
            timestamp=timestamp,
            extra_raw_data=extra or None,
        )
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, "message_dict") else str(exc)
        return {"ok": False, "body": {"errors": detail, "log": _gateway_log_ref(item)}}
    return {
        "ok": True,
        "body": {
            "id": punch.id,
            "external_id": punch.external_id,
            "timestamp": punch.timestamp.isoformat(),
            "employee_id": punch.external_employee_id,
            "serial_number": serial_number,
        },
    }


def _gateway_log_ref(item: dict) -> dict:
    return {
        key: item.get(key)
        for key in ("id", "gateway_log_id", "serial_number")
        if key in item
    }