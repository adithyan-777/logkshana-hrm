from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from dashboard.selectors import dashboard_summary_get


@login_required
@require_http_methods(["GET"])
def dashboard_view(request: HttpRequest) -> HttpResponse:
    summary = dashboard_summary_get()
    return render(
        request,
        "dashboard/index.html",
        {
            "summary": summary,
            "chart_data": summary.attendance_chart_data(),
            "greeting_name": request.user.get_short_name() or request.user.get_username(),
        },
    )


@login_required
@require_http_methods(["GET"])
def dashboard_attendance_chart_partial(request: HttpRequest) -> HttpResponse:
    summary = dashboard_summary_get()
    return render(
        request,
        "dashboard/partials/attendance_chart.html",
        {"chart_data": summary.attendance_chart_data()},
    )
