from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_tenants.utils import get_public_schema_name

from dashboard.selectors import dashboard_summary_get


def _is_public_tenant(request: HttpRequest) -> bool:
    tenant = getattr(request, "tenant", None)
    return getattr(tenant, "schema_name", None) == get_public_schema_name()


@login_required
@require_http_methods(["GET"])
def dashboard_view(request: HttpRequest) -> HttpResponse:
    if _is_public_tenant(request):
        return render(request, "dashboard/public.html")

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
    if _is_public_tenant(request):
        return HttpResponse(
            "Attendance is only available in a company workspace.",
            status=404,
        )

    summary = dashboard_summary_get()
    return render(
        request,
        "dashboard/index.html#attendance_chart",
        {"chart_data": summary.attendance_chart_data()},
    )
