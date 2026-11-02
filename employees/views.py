from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError, Q
from django.forms.forms import NON_FIELD_ERRORS
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from attendance.models import Attendance, AttendanceActivity
from attendance.selectors import attendance_activity_list
from attendance.services import activity_create
from common.http import (
    delete_blocked_response,
    is_htmx_partial,
    redirect_to_list_drawer,
    set_error_toast,
    set_hx_trigger,
)
from common.localtime import local_date, local_dt
from common.pagination import list_pagination_context, paginate_queryset
from common.views import redirect_stale_fragment_visit
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


def _duration_label(value: timedelta) -> str:
    total_minutes = max(0, int(value.total_seconds() // 60))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _timeline_segment(start, end, day: date, *, kind: str) -> dict | None:
    """Return one clipped interval for a local 24-hour attendance timeline."""
    local_start = local_dt(start)
    local_end = local_dt(end)
    if (
        local_start.date() > day
        or local_end.date() < day
        or local_end <= local_start
    ):
        return None

    start_seconds = (
        0
        if local_start.date() < day
        else (
            local_start.hour * 3600
            + local_start.minute * 60
            + local_start.second
            + local_start.microsecond / 1_000_000
        )
    )
    end_seconds = (
        86_400
        if local_end.date() > day
        else (
            local_end.hour * 3600
            + local_end.minute * 60
            + local_end.second
            + local_end.microsecond / 1_000_000
        )
    )
    end_seconds = min(86_400, end_seconds)
    duration_seconds = end_seconds - start_seconds
    if duration_seconds <= 0:
        return None

    start_label = (
        f"{int(start_seconds // 3600):02d}:"
        f"{int(start_seconds % 3600 // 60):02d}:"
        f"{int(start_seconds % 60):02d}"
    )
    end_label = (
        "24:00:00"
        if end_seconds == 86_400
        else (
            f"{int(end_seconds // 3600):02d}:"
            f"{int(end_seconds % 3600 // 60):02d}:"
            f"{int(end_seconds % 60):02d}"
        )
    )
    if duration_seconds >= 3600:
        hours, remainder = divmod(int(duration_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        duration_label = f"{hours}h {minutes:02d}m {seconds:02d}s"
    elif duration_seconds >= 60:
        minutes, seconds = divmod(int(duration_seconds), 60)
        duration_label = f"{minutes}m {seconds:02d}s"
    else:
        duration_label = f"{int(duration_seconds)}s"
    return {
        "kind": kind,
        "left": round(start_seconds / 86_400 * 100, 6),
        "width": round(duration_seconds / 86_400 * 100, 6),
        "lane": 0,
        "top": 3,
        "label": f"{start_label}–{end_label} · {duration_label}",
        "start_seconds": start_seconds,
        "duration_seconds": duration_seconds,
        "continues_next_day": local_end.date() > day,
    }


def _attendance_timeline(attendance: Attendance | None, day: date) -> list[dict]:
    if attendance is None:
        return []

    segments = []
    now = timezone.now()
    for session in attendance.work_sessions.all():
        segment = _timeline_segment(
            session.check_in,
            session.check_out or now,
            day,
            kind="work",
        )
        if segment:
            segments.append(segment)
    for session in attendance.break_sessions.all():
        segment = _timeline_segment(
            session.break_in,
            session.break_out or now,
            day,
            kind="break",
        )
        if segment:
            segments.append(segment)
    segments.sort(key=lambda segment: (segment["left"], segment["kind"]))
    lane_ends = []
    for segment in segments:
        start_seconds = segment["start_seconds"]
        visible_end = start_seconds + max(segment["duration_seconds"], 900)
        lane = next(
            (
                index
                for index, lane_end in enumerate(lane_ends)
                if start_seconds >= lane_end
            ),
            len(lane_ends),
        )
        if lane == len(lane_ends):
            lane_ends.append(visible_end)
        else:
            lane_ends[lane] = visible_end
        segment["lane"] = lane
        segment["top"] = 3 + lane * 5
    return segments


def _punches_for_history_days(employee: Employee, punches) -> list[AttendanceActivity]:
    page_punches = list(punches)
    history_days = {
        punch.attendance.day
        if punch.attendance_id and punch.attendance
        else local_date(punch.punch_time)
        for punch in page_punches
    }
    if not history_days:
        return []

    day_filter = Q(attendance__day__in=history_days)
    # Naive wall-clock boundaries: with USE_TZ = False, punch_time is stored
    # as naive Asia/Qatar local, so a naive midnight-to-midnight window
    # matches exactly (make_aware/aware comparisons would pass through
    # datetime adaptation and can shift under the DB session timezone).
    for day in history_days:
        start = datetime.combine(day, time.min)
        end = datetime.combine(day + timedelta(days=1), time.min)
        day_filter |= Q(
            attendance__isnull=True,
            punch_time__gte=start,
            punch_time__lt=end,
        )

    return list(
        attendance_activity_list(employee=employee)
        .filter(day_filter)
        .select_related("attendance")
        .order_by("-punch_time", "-pk")
    )


def _employee_punch_days(punches) -> list[dict]:
    punch_rows = list(punches)
    attendance_ids = {
        punch.attendance_id for punch in punch_rows if punch.attendance_id
    }
    attendance_by_id = {
        attendance.pk: attendance
        for attendance in Attendance.objects.filter(
            pk__in=attendance_ids
        ).prefetch_related("work_sessions", "break_sessions")
    }

    days = {}
    for punch in punch_rows:
        attendance = attendance_by_id.get(punch.attendance_id)
        day = (
            attendance.day
            if attendance
            else local_date(punch.punch_time)
        )
        group = days.setdefault(
            day,
            {
                "date": day,
                "attendance": attendance,
                "punches": [],
            },
        )
        if group["attendance"] is None and attendance is not None:
            group["attendance"] = attendance
        group["punches"].append(punch)

    result = []
    for day in sorted(days, reverse=True):
        group = days[day]
        attendance = group["attendance"]
        events = sorted(
            group["punches"], key=lambda punch: (punch.punch_time, punch.pk)
        )
        group.update(
            {
                "punches": events,
                "punch_count": len(events),
                "first_punch": events[0].punch_time,
                "last_punch": events[-1].punch_time,
                "status": (
                    attendance.get_status_display() if attendance else "Punches only"
                ),
                "worked_time": (
                    _duration_label(attendance.total_work_time) if attendance else "—"
                ),
                "break_time": (
                    _duration_label(attendance.total_break_time) if attendance else "—"
                ),
                "overtime": (
                    _duration_label(attendance.over_time) if attendance else "—"
                ),
                "late_time": (
                    _duration_label(attendance.late_time) if attendance else "—"
                ),
                "early_leave_time": (
                    _duration_label(attendance.early_leave_time)
                    if attendance
                    else "—"
                ),
                "timeline": _attendance_timeline(attendance, day),
            }
        )
        group["has_next_day_punches"] = any(
            local_date(punch.punch_time) > day for punch in events
        )
        group["timeline_continues_next_day"] = any(
            segment["continues_next_day"] for segment in group["timeline"]
        )
        result.append(group)
    return result


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
@require_permission(PermissionCodename.EMPLOYEES_VIEW)
@require_http_methods(["GET"])
def employee_detail_view(request: HttpRequest, employee_id: int) -> HttpResponse:
    employee = employee_get(employee_id=employee_id)
    if employee is None:
        raise Http404

    active_tab = "attendance" if request.GET.get("tab") == "attendance" else "overview"
    detail_url = reverse("employee_detail", args=[employee.pk])
    can_view_attendance = user_has_permission(
        user=request.user, codename=PermissionCodename.ATTENDANCE_VIEW
    )
    context = {
        "employee": employee,
        "active_tab": active_tab,
        "detail_url": detail_url,
        "can_edit": user_has_permission(
            user=request.user, codename=PermissionCodename.EMPLOYEES_EDIT
        ),
        "can_punch": user_has_permission(
            user=request.user, codename=PermissionCodename.ATTENDANCE_ADD
        ),
        "can_view_attendance": can_view_attendance,
        "breadcrumbs": [
            ("Dashboard", "dashboard"),
            ("Employees", "employee_list"),
            (employee.full_name, None),
        ],
    }
    if active_tab == "attendance" and can_view_attendance:
        history_all = request.GET.get("range") == "all"
        history_from = history_to = None
        history_date_error = ""
        if not history_all:
            today = local_date()
            default_from = today - timedelta(days=6)
            try:
                history_from = (
                    date.fromisoformat(request.GET["from"])
                    if request.GET.get("from")
                    else default_from
                )
                history_to = (
                    date.fromisoformat(request.GET["to"])
                    if request.GET.get("to")
                    else today
                )
            except ValueError:
                history_from, history_to = default_from, today
                history_date_error = (
                    "Enter valid start and end dates. Showing the last 7 days."
                )
            if history_from > history_to:
                history_from, history_to = history_to, history_from
                history_date_error = (
                    "The date range was reversed, so it has been adjusted."
                )

        punches = attendance_activity_list(
            employee=employee,
            day_from=None if history_all else history_from,
            day_to=None if history_all else history_to,
        ).select_related("attendance")
        punches = punches.order_by("-punch_time", "-pk")
        page_obj = paginate_queryset(request, punches)
        punch_rows = list(page_obj.object_list)
        page_obj.object_list = punch_rows
        history_punches = _punches_for_history_days(employee, punch_rows)
        context.update(
            {
                "punches": punch_rows,
                "punch_days": _employee_punch_days(history_punches),
                "page_obj": page_obj,
                "pagination_mode": "links",
                "history_all": history_all,
                "history_from": history_from,
                "history_to": history_to,
                "history_date_error": history_date_error,
            }
        )
        if page_obj.has_previous():
            page_query = {
                "tab": "attendance",
                "page": page_obj.previous_page_number(),
            }
            if history_all:
                page_query["range"] = "all"
            else:
                page_query["from"] = history_from.isoformat()
                page_query["to"] = history_to.isoformat()
            query = urlencode(page_query)
            context["prev_page_url"] = f"{detail_url}?{query}"
        if page_obj.has_next():
            page_query = {
                "tab": "attendance",
                "page": page_obj.next_page_number(),
            }
            if history_all:
                page_query["range"] = "all"
            else:
                page_query["from"] = history_from.isoformat()
                page_query["to"] = history_to.isoformat()
            query = urlencode(page_query)
            context["next_page_url"] = f"{detail_url}?{query}"

    if is_htmx_partial(request):
        fragment = request.GET.get("fragment")
        if fragment == "detail":
            response = render(
                request, "employees/detail.html#employee_detail_page", context
            )
            response["HX-Push-Url"] = "false"
            return response
        if fragment == "attendance" and active_tab == "attendance":
            response = render(
                request,
                "employees/partials/detail_attendance.html#employee_attendance",
                context,
            )
            response["HX-Push-Url"] = "false"
            return response
    return render(request, "employees/detail.html", context)


@login_required
@require_permission(PermissionCodename.ATTENDANCE_ADD)
@require_http_methods(["POST"])
def employee_punch_toggle(request: HttpRequest, employee_id: int) -> HttpResponse:
    """Record the next web punch for an employee (attendance.add only).

    The next punch direction is the inverse of the employee's mirrored
    state (punched out ⇒ IN, punched in ⇒ OUT; suspended states close
    their sub-period first). The punch itself goes through
    ``activity_create`` — the exact same path as a manual punch from
    the Record-punch form — so pairing, day rows, and the status
    mirror all update through the regular pipeline.

    Return the refreshed button and notify the employee detail page.
    """
    employee = get_object_or_404(Employee, pk=employee_id)
    activity_create(
        employee=employee,
        punch_time=timezone.now(),
        direction=employee.next_punch_direction,
        method=AttendanceActivity.AttendanceActivityMethodType.WEB,
    )
    employee.refresh_from_db()
    response = render(
        request,
        "partials/punch_status_badge.html",
        {"employee": employee, "can_punch": True},
    )
    set_hx_trigger(
        response,
        event="employeePunchUpdated",
        toast="Punch recorded.",
        close_modal=False,
    )
    return response


@login_required
@require_http_methods(["GET"])
def employee_options_view(request: HttpRequest) -> HttpResponse:
    """HTMX fragment: searchable employee options (min 2 chars).

    Used by attendance forms (Add/Edit correction, Record/Edit punch)
    and schedule assignment forms (multi-select).
    Accepts ``?q=`` (or ``?employee_q=`` from the combobox input).
    With ``?mode=multi&target=<box-id>`` returns Add-button options
    for the multi-select widget instead of single-select options.
    Returns a small HTML fragment for ``#employee-results``.
    Non-HTMX visits reload out like ``select_options_view`` — calls must
    carry the ``HX-Request`` header.
    """
    if not is_htmx_partial(request):
        return redirect_stale_fragment_visit(
            request,
            fallback_url_name="dashboard",
            follow_referer=True,
            fragment_path="/employees/options/",
        )
    allowed = (
        user_has_permission(user=request.user, codename=PermissionCodename.ATTENDANCE_ADD)
        or user_has_permission(user=request.user, codename=PermissionCodename.ATTENDANCE_VIEW)
        or user_has_permission(user=request.user, codename=PermissionCodename.EMPLOYEES_VIEW)
        or user_has_permission(user=request.user, codename=PermissionCodename.SCHEDULE_VIEW)
        or user_has_permission(user=request.user, codename=PermissionCodename.SCHEDULE_ADD)
    )
    if not allowed:
        raise PermissionDenied
    q = request.GET.get("q", request.GET.get("employee_q", "")).strip()
    target = request.GET.get("target", "")
    if not q and request.GET.get("mode") == "multi" and target:
        # Each multi-select search box has its own input name so two
        # pickers can share one form without clobbering each other.
        q = request.GET.get(f"{target}_q", "").strip()
    if len(q) < 2:
        return HttpResponse("")
    employees = list(
        Employee.objects.filter(is_active=True)
        .filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(emp_code__icontains=q)
            | Q(email__icontains=q)
        )
        .order_by("first_name", "last_name")[:20]
    )
    if request.GET.get("mode") == "multi":
        return render(
            request,
            "partials/employee_multi_options.html",
            {
                "query": q,
                "employees": employees,
                "target": target,
            },
        )
    return render(
        request,
        "partials/employee_options.html",
        {"query": q, "employees": employees, "too_short": False},
    )


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
            set_hx_trigger(
                response,
                event="employeeCreated",
                toast="Employee added. Share the invite link to set their password.",
                close_modal=False,
            )
            return response

        return _render_form(request, form)

    form = EmployeeForm()
    if is_htmx_partial(request):
        return _render_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="employee_list",
        form_url=reverse("employee_add"),
        title="Add employee",
        size="wide",
    )


def _form_error_message(form) -> str:
    """One-line summary of a form's validation errors for an error toast."""
    parts = []
    for field, messages in form.errors.items():
        if field == NON_FIELD_ERRORS:
            parts.extend(str(message) for message in messages)
        else:
            label = form.fields[field].label or field
            parts.extend(f"{label}: {message}" for message in messages)
    return "; ".join(parts) or "Please fix the errors below."


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
            # close_modal=True (default): drawer closes; employeeUpdated
            # still refreshes the list behind it; toast confirms the save.
            set_hx_trigger(
                response,
                event="employeeUpdated",
                toast=f"Employee “{employee.full_name}” updated.",
            )
            return response

        # Invalid: keep the drawer open (no closeModal), show the errors
        # inline AND as an error toast.
        response = _render_edit_form(request, form, employee=employee)
        set_error_toast(response, _form_error_message(form))
        return response

    form = EmployeeForm(instance=employee)
    if is_htmx_partial(request):
        return _render_edit_form(request, form, employee=employee)

    return redirect_to_list_drawer(
        list_url_name="employee_list",
        form_url=request.path,
        title="Edit employee",
        size="wide",
    )


@login_required
@require_permission(PermissionCodename.EMPLOYEES_DELETE)
@require_http_methods(["DELETE"])
def employee_delete_view(request: HttpRequest, employee_id: int) -> HttpResponse:
    employee = employee_get(employee_id=employee_id)
    if employee is None:
        raise Http404
    try:
        employee_delete(employee=employee)
    except ProtectedError:
        return delete_blocked_response(
            "Cannot delete employee: they still have leave requests."
        )
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
            set_hx_trigger(
                response,
                event="departmentCreated",
                toast=f"Department “{form.cleaned_data['name']}” created.",
            )
            return response

        return _render_department_form(request, form)

    form = DepartmentForm()
    if is_htmx_partial(request):
        return _render_department_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="department_list",
        form_url=reverse("department_add"),
        title="Add department",
    )


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

    return redirect_to_list_drawer(
        list_url_name="department_list",
        form_url=request.path,
        title="Edit department",
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
            set_hx_trigger(
                response,
                event="positionCreated",
                toast=f"Position “{form.cleaned_data['title']}” created.",
            )
            return response

        return _render_position_form(request, form)

    form = PositionForm()
    if is_htmx_partial(request):
        return _render_position_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="position_list",
        form_url=reverse("position_add"),
        title="Add position",
    )


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

    return redirect_to_list_drawer(
        list_url_name="position_list",
        form_url=request.path,
        title="Edit position",
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
            set_hx_trigger(
                response,
                event="roleCreated",
                toast=f"Role “{form.cleaned_data['name']}” created.",
            )
            return response

        return _render_role_form(request, form)

    form = RoleForm()
    if is_htmx_partial(request):
        return _render_role_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="role_list",
        form_url=reverse("role_add"),
        title="Add role",
    )


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
            set_hx_trigger(
                response,
                event="permissionCreated",
                toast=f"Permission “{form.cleaned_data['codename']}” created.",
            )
            return response

        return _render_permission_form(request, form)

    form = PermissionForm()
    if is_htmx_partial(request):
        return _render_permission_form(request, form)

    return redirect_to_list_drawer(
        list_url_name="permission_list",
        form_url=reverse("permission_add"),
        title="Add permission",
    )
