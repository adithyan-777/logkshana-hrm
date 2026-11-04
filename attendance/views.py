import json
import logging
from functools import wraps

import sentry_sdk
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from attendance.calculation import direction_from_gateway_status_label
from attendance.forms import (
    AttendanceActivityForm,
    AttendanceCorrectionForm,
    AttendanceForm,
)
from attendance.integrations.gateway import gateway_request_is_authorized
from attendance.models import Attendance, AttendanceActivity, WorkSession
from attendance.selectors import (
    attendance_activity_list,
    attendance_exception_day_list,
    attendance_list,
    work_session_list,
)
from attendance.services import (
    activity_correction_create,
    activity_create,
    activity_delete,
    activity_update,
    attendance_record_create,
    attendance_record_delete,
    attendance_record_update,
)
from common.http import (
    delete_blocked_response,
    is_htmx_partial,
    redirect_to_list_drawer,
    set_hx_trigger,
)
from common.localtime import local_date
from common.pagination import list_pagination_context
from employees.decorators import require_permission
from employees.permission_catalog import PermissionCodename
from employees.selectors import employee_get_for_user, user_has_permission

logger = logging.getLogger("attendance.gateway")


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
    for field_name in ("punch_time",):
        if field_name in form.fields:
            form.fields[field_name].input_formats = datetime_formats


def _selected_employee_label(form) -> str:
    """Display label for the combobox's current employee value."""
    employee = None
    try:
        if form.is_bound:
            raw_id = form.data.get("employee")
            if raw_id:
                from employees.models import Employee

                employee = Employee.objects.filter(pk=raw_id).first()
        elif getattr(getattr(form, "instance", None), "employee_id", None):
            employee = form.instance.employee
    except Exception:
        employee = None
    if employee is None:
        return ""
    return f"{employee.emp_code} - {employee.full_name}"


def _cleaned_without_search(form):
    data = dict(form.cleaned_data)
    data.pop("employee_q", None)
    return data


def _render_transaction_form(
    request: HttpRequest, form: AttendanceActivityForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "attendance/transaction_add.html#transaction_form",
        {
            "form": form,
            "success_message": success_message,
            "selected_label": _selected_employee_label(form),
        },
    )


def _render_daily_form(
    request: HttpRequest, form: AttendanceForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "attendance/daily_add.html#daily_form",
        {
            "form": form,
            "success_message": success_message,
            "selected_label": _selected_employee_label(form),
        },
    )


@login_required
@require_permission(PermissionCodename.ATTENDANCE_VIEW)
@require_http_methods(["GET"])
def transaction_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        attendance_activity_list(search=search),
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
@require_permission(PermissionCodename.ATTENDANCE_VIEW)
@require_http_methods(["GET"])
def anomaly_list_view(request: HttpRequest) -> HttpResponse:
    """Punch-flow exception queue (TimeTrex-style, passive first pass).

    Day-centric work queue: one row per (employee, day) with punch-flow
    problems — missing check-out on a past day, stray check-outs,
    duplicate punches — with corrections as the resolution path (the
    row links straight to that employee's punches). Today's open
    sessions are work-in-progress, not exceptions.
    """
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    date_from = _parse_date_filter(request.GET.get("from"))
    date_to = _parse_date_filter(request.GET.get("to"))
    entries = attendance_exception_day_list(
        search=search,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    unresolved_count = sum(1 for e in entries if e["has_problems"])
    # page_obj + pagination_* land at top level for the template.
    context = {
        "search": search,
        "status": status,
        "date_from": date_from,
        "date_to": date_to,
        "unresolved_count": unresolved_count,
    }
    context.update(
        list_pagination_context(
            request,
            entries,
            search=search,
            base_url=reverse("attendance_anomalies"),
            hx_target="#anomaly-list",
        )
    )

    if is_htmx_partial(request):
        return render(
            request, "attendance/anomaly_list.html#anomaly_table", context
        )

    return render(request, "attendance/anomaly_list.html", context)


def _parse_date_filter(raw: str | None):
    from datetime import date as date_cls

    if not raw:
        return None
    try:
        return date_cls.fromisoformat(raw)
    except ValueError:
        return None


@login_required
@require_permission(PermissionCodename.ATTENDANCE_VIEW)
@require_http_methods(["GET"])
def work_session_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        work_session_list(search=search),
        search=search,
        base_url=reverse("work_session_list"),
        hx_target="#work-session-list",
    )

    if is_htmx_partial(request):
        return render(
            request, "attendance/work_session_list.html#work_session_table", context
        )

    return render(request, "attendance/work_session_list.html", context)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_ADD)
@require_http_methods(["GET", "POST"])
def transaction_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = AttendanceActivityForm(request.POST)
        _configure_datetime_fields(form)
        if form.is_valid():
            activity_create(**_cleaned_without_search(form))
            form = AttendanceActivityForm()
            _configure_datetime_fields(form)
            response = _render_transaction_form(
                request,
                form,
                success_message="Attendance punch recorded.",
            )
            response["HX-Trigger"] = "attendanceTransactionCreated"
            return response

        return _render_transaction_form(request, form)

    form = AttendanceActivityForm()
    _configure_datetime_fields(form)
    if is_htmx_partial(request):
        return _render_transaction_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="attendance_transaction_list",
        form_url=reverse("attendance_transaction_add"),
        title="Record punch",
    )


def _render_transaction_edit_form(
    request: HttpRequest, form: AttendanceActivityForm, *, transaction
) -> HttpResponse:
    return render(
        request,
        "attendance/transaction_edit.html#transaction_edit_form",
        {
            "form": form,
            "transaction": transaction,
            "selected_label": _selected_employee_label(form),
        },
    )


def _render_transaction_correct_form(
    request: HttpRequest, form: AttendanceCorrectionForm, *, transaction
) -> HttpResponse:
    return render(
        request,
        "attendance/transaction_correct.html#transaction_correct_form",
        {
            "form": form,
            "transaction": transaction,
            "selected_label": _selected_employee_label(form),
        },
    )


def _correction_impact(transaction) -> dict:
    """Derived rows the day repair will delete and rebuild.

    Same-day WorkSessions plus every open session of the employee (an
    open session from any earlier day is the overnight case the repair
    also wipes and re-pairs), and the Attendance day rows involved.
    Read-only preview for the review step of the correction drawer.
    The day is the wall-clock (local) day — same normalization the
    repair itself uses.
    """
    employee = transaction.employee
    day = local_date(transaction.punch_time)
    sessions = list(
        WorkSession.objects.filter(
            Q(employee=employee, day=day) | Q(employee=employee, check_out__isnull=True)
        )
        .select_related("attendance", "in_punch", "out_punch")
        .order_by("day", "check_in")
    )
    session_days = {session.day for session in sessions} | {day}
    records = list(
        Attendance.objects.filter(employee=employee, day__in=session_days).order_by(
            "day"
        )
    )
    return {"sessions": sessions, "records": records, "days": sorted(session_days)}


def _render_transaction_correct_review(
    request: HttpRequest, transaction
) -> HttpResponse:
    return render(
        request,
        "attendance/transaction_correct.html#transaction_correct_review",
        {
            "transaction": transaction,
            "impact": _correction_impact(transaction),
        },
    )


def _readonly_punch_toast_response(*, message: str) -> HttpResponse:
    """Empty swap with an error toast + drawer close.

    Used to refuse operations on gateway-managed (biometric) punches
    from HTMX flows; the UI hides the controls, so this only fires on
    stale markup or a hand-crafted request.
    """
    response = HttpResponse("")
    response["HX-Trigger"] = json.dumps(
        {"closeModal": True, "showToast": {"message": message, "type": "error"}}
    )
    return response


@login_required
@require_permission(PermissionCodename.ATTENDANCE_ADD)
@require_http_methods(["GET", "POST"])
def transaction_edit(request: HttpRequest, transaction_id: int) -> HttpResponse:
    transaction = get_object_or_404(AttendanceActivity, pk=transaction_id)
    if not transaction.is_editable:
        # Gateway punches are read-only: the tab hides the edit/delete
        # controls; this guard covers stale markup + direct requests.
        if is_htmx_partial(request):
            return _readonly_punch_toast_response(
                message=(
                    "Biometric punches can't be edited —"
                    " they come from the device gateway."
                ),
            )
        return redirect_to_list_drawer(
            list_url_name="attendance_transaction_list",
            form_url=reverse("attendance_transaction_add"),
            title="Record punch",
        )

    if request.method == "POST":
        form = AttendanceActivityForm(request.POST, instance=transaction)
        _configure_datetime_fields(form)
        if form.is_valid():
            activity_update(**_cleaned_without_search(form), activity=transaction)
            response = _render_transaction_edit_form(
                request,
                AttendanceActivityForm(instance=transaction),
                transaction=transaction,
            )
            # Closed-drawer UX: toast + closeModal ride along with the
            # update event (the list refreshes on transactionUpdated).
            set_hx_trigger(
                response,
                event="transactionUpdated",
                toast=(
                    f"Punch updated for {transaction.employee.full_name}"
                    f" at {transaction.punch_time:%Y-%m-%d %H:%M}."
                ),
            )
            return response

        return _render_transaction_edit_form(request, form, transaction=transaction)

    form = AttendanceActivityForm(instance=transaction)
    _configure_datetime_fields(form)
    if is_htmx_partial(request):
        return _render_transaction_edit_form(request, form, transaction=transaction)

    return redirect_to_list_drawer(
        list_url_name="attendance_transaction_list",
        form_url=request.path,
            title="Edit punch",
        )


@login_required
@require_permission(PermissionCodename.ATTENDANCE_ADD)
@require_http_methods(["GET", "POST"])
def transaction_correct(request: HttpRequest, transaction_id: int) -> HttpResponse:
    """Direction-only correction for a gateway (biometric) punch.

    Edit/delete are refused for biometric punches (the device is the
    source of truth), but a correction is recorded as a NEW punch row
    (method=correction); the original stays in the log and simply points
    at its correction. Employee and punch time are inherited — the form
    only offers the direction.
    """
    transaction = get_object_or_404(AttendanceActivity, pk=transaction_id)
    if not transaction.is_correctable:
        already_corrected = (
            transaction.method
            == AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC
        )
        message = (
            "This punch already has a correction."
            if already_corrected
            else "Only biometric punches can be corrected."
        )
        if is_htmx_partial(request):
            return _readonly_punch_toast_response(message=message)
        return redirect_to_list_drawer(
            list_url_name="attendance_transaction_list",
            form_url=reverse("attendance_transaction_add"),
            title="Record punch",
        )

    if request.method == "POST":
        form = AttendanceCorrectionForm(request.POST, instance=transaction)
        if form.is_valid():
            correction = activity_correction_create(
                original=transaction,
                direction=form.cleaned_data["direction"],
                corrected_by=request.user,
            )
            response = HttpResponse("")
            set_hx_trigger(
                response,
                event="transactionUpdated",
                toast=(
                    f"Correction recorded for {correction.employee.full_name}"
                    f" at {correction.punch_time:%Y-%m-%d %H:%M}."
                ),
            )
            return response
        return _render_transaction_correct_form(request, form, transaction=transaction)

    if is_htmx_partial(request):
        if request.GET.get("step") == "form":
            form = AttendanceCorrectionForm(instance=transaction)
            return _render_transaction_correct_form(
                request, form, transaction=transaction
            )
        return _render_transaction_correct_review(request, transaction)

    return redirect_to_list_drawer(
        list_url_name="attendance_transaction_list",
        form_url=request.path,
        title="Correct punch",
    )


@login_required
@require_permission(PermissionCodename.ATTENDANCE_DELETE)
@require_http_methods(["DELETE"])
def transaction_delete_view(request: HttpRequest, transaction_id: int) -> HttpResponse:
    transaction = get_object_or_404(AttendanceActivity, pk=transaction_id)
    if not transaction.is_editable:
        return delete_blocked_response(
            message=(
                "Biometric punches can't be deleted —"
                " they come from the device gateway."
            ),
        )
    activity_delete(activity=transaction)
    response = HttpResponse("")
    response["HX-Trigger"] = "transactionDeleted"
    return response


@login_required
@require_permission(PermissionCodename.ATTENDANCE_VIEW)
@require_http_methods(["GET"])
def daily_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        attendance_list(search=search),
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
        form = AttendanceForm(request.POST)
        if form.is_valid():
            attendance_record_create(**_cleaned_without_search(form))
            response = _render_daily_form(
                request,
                AttendanceForm(),
                success_message="Correction created.",
            )
            response["HX-Trigger"] = "dailyAttendanceCreated"
            return response

        return _render_daily_form(request, form)

    form = AttendanceForm()
    if is_htmx_partial(request):
        return _render_daily_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="daily_attendance_list",
        form_url=reverse("daily_attendance_add"),
        title="Add correction",
    )


def _render_daily_edit_form(
    request: HttpRequest, form: AttendanceForm, *, daily_attendance
) -> HttpResponse:
    return render(
        request,
        "attendance/daily_edit.html#daily_edit_form",
        {
            "form": form,
            "daily_attendance": daily_attendance,
            "selected_label": _selected_employee_label(form),
        },
    )


@login_required
@require_permission(PermissionCodename.ATTENDANCE_ADD)
@require_http_methods(["GET", "POST"])
def daily_edit(request: HttpRequest, daily_id: int) -> HttpResponse:
    daily_attendance = get_object_or_404(Attendance, pk=daily_id)

    if request.method == "POST":
        form = AttendanceForm(request.POST, instance=daily_attendance)
        if form.is_valid():
            attendance_record_update(
                **_cleaned_without_search(form), attendance=daily_attendance
            )
            response = _render_daily_edit_form(
                request,
                AttendanceForm(instance=daily_attendance),
                daily_attendance=daily_attendance,
            )
            response["HX-Trigger"] = "dailyUpdated"
            return response

        return _render_daily_edit_form(request, form, daily_attendance=daily_attendance)

    form = AttendanceForm(instance=daily_attendance)
    if is_htmx_partial(request):
        return _render_daily_edit_form(request, form, daily_attendance=daily_attendance)

    return redirect_to_list_drawer(
        list_url_name="daily_attendance_list",
        form_url=request.path,
            title="Edit correction",
        )


@login_required
@require_permission(PermissionCodename.ATTENDANCE_DELETE)
@require_http_methods(["DELETE"])
def daily_delete_view(request: HttpRequest, daily_id: int) -> HttpResponse:
    daily_attendance = get_object_or_404(Attendance, pk=daily_id)
    try:
        attendance_record_delete(attendance=daily_attendance)
    except DjangoValidationError as exc:
        return delete_blocked_response("; ".join(exc.messages))
    response = HttpResponse("")
    response["HX-Trigger"] = "dailyDeleted"
    return response


@login_required
@require_permission(PermissionCodename.ATTENDANCE_OWN_VIEW)
@require_http_methods(["GET"])
def my_attendance_view(request: HttpRequest) -> HttpResponse:
    employee = employee_get_for_user(user=request.user)
    search = request.GET.get("q", "").strip()
    if employee is None:
        queryset = Attendance.objects.none()
        recent_punches: list = []
    else:
        queryset = attendance_list(search=search, employee=employee)
        recent_punches = list(attendance_activity_list(employee=employee)[:10])
    context = list_pagination_context(
        request,
        queryset,
        search=search,
        base_url=reverse("my_attendance"),
        hx_target="#my-attendance-list",
    )
    context["employee"] = employee
    context["recent_punches"] = recent_punches

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
    """
    from companies.services import attendance_log_create

    try:
        payload = json.loads(request.body or b"")
    except (json.JSONDecodeError, UnicodeDecodeError):
        _log_gateway_rejection(
            None, {"body": "Invalid JSON body."}
        )
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


def _log_gateway_rejection(item, errors):
    """ERROR-log a rejected gateway push and raise a Sentry issue."""
    ref = _gateway_log_ref(item) if item else {}
    logger.error(
        "Gateway push rejected: %s (serial=%s, log_id=%s)",
        errors,
        ref.get("serial_number"),
        ref.get("gateway_log_id"),
    )
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("gateway.rejected", True)
        scope.set_extra("errors", errors)
        scope.set_extra("payload", item)
        sentry_sdk.capture_message("Gateway push rejected", level="error")


def _parse_gateway_datetime(value):
    """Parse a gateway timestamp with entry/error/result logging."""
    logger.info("Parsing gateway timestamp: %r", value)
    try:
        parsed = parse_datetime(value)
    except ValueError:
        logger.error(
            "ValueError parsing gateway timestamp: %r", value, exc_info=True
        )
        raise
    logger.info("Gateway timestamp parsed: %r -> %s", value, parsed)
    return parsed


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
    logger.info(
        "Gateway push item timestamp raw: %r (serial=%s, user_id=%s)",
        timestamp_raw,
        serial_number,
        employee_id,
    )
    timestamp = _parse_gateway_datetime(str(timestamp_raw)) if timestamp_raw else None
    logger.info("Gateway push item timestamp result: %s", timestamp)
    if timestamp is None:
        errors["timestamp"] = "Enter a valid datetime."
    if errors:
        _log_gateway_rejection(item, errors)
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
    label = item.get("status_label")
    if direction_from_gateway_status_label(label) == "in":
        logger.info(
            "Gateway push item check-in punch (serial=%s, user_id=%s, "
            "status_label=%r, timestamp=%s)",
            serial_number,
            employee_id,
            label,
            timestamp,
        )
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
        _log_gateway_rejection(item, detail)
        return {"ok": False, "body": {"errors": detail, "log": _gateway_log_ref(item)}}
    return {
        "ok": True,
        "body": {
            "id": punch.id,
            "external_id": punch.external_id,
            "timestamp": punch.punch_time.isoformat(),
            # punch.employee is NOT fetched here: attendance_log_create()
            # returns from inside schema_context(tenant_schema), so a lazy
            # FK would query the request's (non-tenant) schema and raise
            # Employee.DoesNotExist. employee_id is the payload value
            # already resolved inside the tenant schema.
            "employee_id": str(employee_id),
            "serial_number": serial_number,
        },
    }


def _gateway_log_ref(item: dict) -> dict:
    return {
        key: item.get(key)
        for key in ("id", "gateway_log_id", "serial_number")
        if key in item
    }
