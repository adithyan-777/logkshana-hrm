from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from common.http import is_htmx_partial
from common.pagination import paginate_queryset
from employees.decorators import require_permission
from employees.permission_catalog import PermissionCodename
from reports.exports import render_report_response
from reports.forms import (
    DateRangeFilterForm,
    ExceptionReportFilterForm,
    IndividualReportFilterForm,
    LeaveReportFilterForm,
    OvertimeReportFilterForm,
)
from reports.report_data import (
    attendance_summary_report_data,
    department_attendance_report_data,
    exception_report_data,
    individual_attendance_report_data,
    leave_balance_report_data,
    leave_utilization_report_data,
    overtime_report_data,
    pending_leave_report_data,
    punch_log_report_data,
)
from reports.selectors.attendance import (
    attendance_summary_list,
    department_attendance_list,
    individual_attendance_list,
)
from reports.selectors.exceptions import exception_report_list
from reports.selectors.leave import (
    leave_balance_list,
    leave_utilization_list,
    pending_leave_list,
)
from reports.selectors.overtime import overtime_report_list
from reports.selectors.punch_log import punch_log_list
from reports.utils import current_month_range, report_pagination_context


def _export_format(request: HttpRequest) -> str:
    return request.GET.get("format", "").strip().lower()


def _build_query_string(request: HttpRequest, *, export_format: str) -> str:
    params = request.GET.copy()
    params["format"] = export_format
    return urlencode(params)


def _maybe_export(
    request: HttpRequest,
    *,
    data,
    filename: str,
) -> HttpResponse | None:
    export_format = _export_format(request)
    if export_format in {"csv", "xlsx", "pdf"}:
        return render_report_response(
            data=data,
            filename=filename,
            export_format=export_format,
        )
    return None


def _filter_context(request: HttpRequest, form, *, report_url_name: str) -> dict:
    return {
        "form": form,
        "report_url_name": report_url_name,
        "export_csv_url": f"?{_build_query_string(request, export_format='csv')}",
        "export_xlsx_url": f"?{_build_query_string(request, export_format='xlsx')}",
        "export_pdf_url": f"?{_build_query_string(request, export_format='pdf')}",
    }


@login_required
@require_permission(PermissionCodename.REPORTS_VIEW)
@require_http_methods(["GET"])
def report_hub_view(request: HttpRequest) -> HttpResponse:
    return render(request, "reports/hub.html")


@login_required
@require_permission(PermissionCodename.REPORTS_VIEW)
@require_http_methods(["GET"])
def attendance_summary_view(request: HttpRequest) -> HttpResponse:
    form = DateRangeFilterForm(request.GET or None)
    date_from, date_to = current_month_range()
    department_id = None
    employee_id = None

    if form.is_valid():
        date_from, date_to = form.cleaned_date_range()
        department_id = (
            form.cleaned_data["department"].pk
            if form.cleaned_data["department"]
            else None
        )
        employee_id = (
            form.cleaned_data["employee"].pk if form.cleaned_data["employee"] else None
        )

    queryset = attendance_summary_list(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        employee_id=employee_id,
    )

    export_response = _maybe_export(
        request,
        data=attendance_summary_report_data(list(queryset)),
        filename="attendance-summary",
    )
    if export_response:
        return export_response

    page_obj = paginate_queryset(request, queryset)
    context = {
        **_filter_context(request, form, report_url_name="report_attendance_summary"),
        **report_pagination_context(request, page_obj),
        "date_from": date_from,
        "date_to": date_to,
    }

    if is_htmx_partial(request):
        return render(
            request, "reports/attendance_summary.html#attendance_summary_table", context
        )

    return render(request, "reports/attendance_summary.html", context)


@login_required
@require_permission(PermissionCodename.REPORTS_VIEW)
@require_http_methods(["GET"])
def individual_attendance_view(request: HttpRequest) -> HttpResponse:
    form = IndividualReportFilterForm(request.GET or None)
    date_from, date_to = current_month_range()
    employee_id = None
    queryset = []

    if form.is_valid():
        date_from, date_to = form.cleaned_date_range()
        if form.cleaned_data["employee"]:
            employee_id = form.cleaned_data["employee"].pk
            queryset = individual_attendance_list(
                date_from=date_from,
                date_to=date_to,
                employee_id=employee_id,
            )

    if employee_id:
        export_response = _maybe_export(
            request,
            data=individual_attendance_report_data(list(queryset)),
            filename="individual-attendance",
        )
        if export_response:
            return export_response

    page_obj = paginate_queryset(request, queryset)
    context = {
        **_filter_context(
            request, form, report_url_name="report_individual_attendance"
        ),
        **report_pagination_context(request, page_obj),
        "date_from": date_from,
        "date_to": date_to,
        "employee_selected": employee_id is not None,
    }

    if is_htmx_partial(request):
        return render(request, "reports/individual.html#individual_table", context)

    return render(request, "reports/individual.html", context)


@login_required
@require_permission(PermissionCodename.REPORTS_VIEW)
@require_http_methods(["GET"])
def department_attendance_view(request: HttpRequest) -> HttpResponse:
    form = DateRangeFilterForm(request.GET or None)
    date_from, date_to = current_month_range()
    department_id = None

    if form.is_valid():
        date_from, date_to = form.cleaned_date_range()
        department_id = (
            form.cleaned_data["department"].pk
            if form.cleaned_data["department"]
            else None
        )

    queryset = department_attendance_list(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
    )

    export_response = _maybe_export(
        request,
        data=department_attendance_report_data(list(queryset)),
        filename="department-attendance",
    )
    if export_response:
        return export_response

    page_obj = paginate_queryset(request, queryset)
    context = {
        **_filter_context(
            request, form, report_url_name="report_department_attendance"
        ),
        **report_pagination_context(request, page_obj),
        "date_from": date_from,
        "date_to": date_to,
    }

    if is_htmx_partial(request):
        return render(request, "reports/department.html#department_table", context)

    return render(request, "reports/department.html", context)


@login_required
@require_permission(PermissionCodename.REPORTS_VIEW)
@require_http_methods(["GET"])
def exception_report_view(request: HttpRequest) -> HttpResponse:
    form = ExceptionReportFilterForm(request.GET or None)
    date_from, date_to = current_month_range()
    department_id = None
    employee_id = None
    exception_type = ""

    if form.is_valid():
        date_from, date_to = form.cleaned_date_range()
        department_id = (
            form.cleaned_data["department"].pk
            if form.cleaned_data["department"]
            else None
        )
        employee_id = (
            form.cleaned_data["employee"].pk if form.cleaned_data["employee"] else None
        )
        exception_type = form.cleaned_data.get("exception_type") or ""

    queryset = exception_report_list(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        employee_id=employee_id,
        exception_type=exception_type,
    )

    export_response = _maybe_export(
        request,
        data=exception_report_data(list(queryset)),
        filename="attendance-exceptions",
    )
    if export_response:
        return export_response

    page_obj = paginate_queryset(request, queryset)
    context = {
        **_filter_context(request, form, report_url_name="report_exceptions"),
        **report_pagination_context(request, page_obj),
        "date_from": date_from,
        "date_to": date_to,
    }

    if is_htmx_partial(request):
        return render(request, "reports/exceptions.html#exceptions_table", context)

    return render(request, "reports/exceptions.html", context)


@login_required
@require_permission(PermissionCodename.REPORTS_VIEW)
@require_http_methods(["GET"])
def punch_log_view(request: HttpRequest) -> HttpResponse:
    form = DateRangeFilterForm(request.GET or None)
    date_from, date_to = current_month_range()
    department_id = None
    employee_id = None

    if form.is_valid():
        date_from, date_to = form.cleaned_date_range()
        department_id = (
            form.cleaned_data["department"].pk
            if form.cleaned_data["department"]
            else None
        )
        employee_id = (
            form.cleaned_data["employee"].pk if form.cleaned_data["employee"] else None
        )

    queryset = punch_log_list(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        employee_id=employee_id,
    )

    export_response = _maybe_export(
        request,
        data=punch_log_report_data(list(queryset)),
        filename="punch-log",
    )
    if export_response:
        return export_response

    page_obj = paginate_queryset(request, queryset)
    context = {
        **_filter_context(request, form, report_url_name="report_punch_log"),
        **report_pagination_context(request, page_obj),
        "date_from": date_from,
        "date_to": date_to,
    }

    if is_htmx_partial(request):
        return render(request, "reports/punch_log.html#punch_log_table", context)

    return render(request, "reports/punch_log.html", context)


@login_required
@require_permission(PermissionCodename.REPORTS_VIEW)
@require_http_methods(["GET"])
def overtime_report_view(request: HttpRequest) -> HttpResponse:
    form = OvertimeReportFilterForm(request.GET or None)
    date_from, date_to = current_month_range()
    department_id = None
    employee_id = None
    status = ""

    if form.is_valid():
        date_from, date_to = form.cleaned_date_range()
        department_id = (
            form.cleaned_data["department"].pk
            if form.cleaned_data["department"]
            else None
        )
        employee_id = (
            form.cleaned_data["employee"].pk if form.cleaned_data["employee"] else None
        )
        status = form.cleaned_data.get("status") or ""

    queryset = overtime_report_list(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        employee_id=employee_id,
        status=status,
    )

    export_response = _maybe_export(
        request,
        data=overtime_report_data(list(queryset)),
        filename="overtime-summary",
    )
    if export_response:
        return export_response

    page_obj = paginate_queryset(request, queryset)
    context = {
        **_filter_context(request, form, report_url_name="report_overtime"),
        **report_pagination_context(request, page_obj),
        "date_from": date_from,
        "date_to": date_to,
    }

    if is_htmx_partial(request):
        return render(request, "reports/overtime.html#overtime_table", context)

    return render(request, "reports/overtime.html", context)


@login_required
@require_permission(PermissionCodename.REPORTS_VIEW)
@require_http_methods(["GET"])
def leave_report_view(request: HttpRequest) -> HttpResponse:
    form = LeaveReportFilterForm(request.GET or None)
    report_type = "balance"
    date_from, date_to = current_month_range()
    year = date_to.year
    department_id = None
    employee_id = None
    queryset = []

    if form.is_valid():
        report_type = form.cleaned_data.get("report_type") or "balance"
        date_from, date_to = form.cleaned_date_range()
        year = form.cleaned_year()
        department_id = (
            form.cleaned_data["department"].pk
            if form.cleaned_data["department"]
            else None
        )
        employee_id = (
            form.cleaned_data["employee"].pk if form.cleaned_data["employee"] else None
        )

    if report_type == "balance":
        queryset = leave_balance_list(
            year=year,
            department_id=department_id,
            employee_id=employee_id,
        )
        export_response = _maybe_export(
            request,
            data=leave_balance_report_data(list(queryset)),
            filename="leave-balance",
        )
    elif report_type == "utilization":
        queryset = leave_utilization_list(
            date_from=date_from,
            date_to=date_to,
            department_id=department_id,
            employee_id=employee_id,
        )
        export_response = _maybe_export(
            request,
            data=leave_utilization_report_data(list(queryset)),
            filename="leave-utilization",
        )
    else:
        queryset = pending_leave_list(
            department_id=department_id,
            employee_id=employee_id,
        )
        export_response = _maybe_export(
            request,
            data=pending_leave_report_data(list(queryset)),
            filename="pending-leave",
        )

    if export_response:
        return export_response

    page_obj = paginate_queryset(request, queryset)
    context = {
        **_filter_context(request, form, report_url_name="report_leave"),
        **report_pagination_context(request, page_obj),
        "report_type": report_type,
        "date_from": date_from,
        "date_to": date_to,
        "year": year,
    }

    if is_htmx_partial(request):
        if report_type == "balance":
            return render(request, "reports/leave.html#leave_balance_table", context)
        return render(request, "reports/leave.html#leave_requests_table", context)

    return render(request, "reports/leave.html", context)
