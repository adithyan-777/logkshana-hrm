from django.urls import NoReverseMatch
from django_tenants.utils import get_public_schema_name

from config.navigation import (
    active_section,
    breadcrumbs_for,
    page_action_for,
    page_heading_for,
    page_subtitle_for,
    topbar_action_for,
)


def navigation(request):
    context = {
        "nav_section": active_section(request),
        "breadcrumbs": breadcrumbs_for(request),
        "page_action": page_action_for(request),
        "page_heading": page_heading_for(request),
        "page_subtitle": page_subtitle_for(request),
        "topbar_action": None,
        "nav_alerts": {
            "pending_leave": 0,
            "pending_overtime": 0,
            "pending_corrections": 0,
            "missing_punch": 0,
        },
    }

    try:
        context["topbar_action"] = topbar_action_for(request)
    except NoReverseMatch:
        context["topbar_action"] = None

    tenant = getattr(request, "tenant", None)
    user = getattr(request, "user", None)
    if (
        tenant is not None
        and getattr(tenant, "schema_name", None) != get_public_schema_name()
        and user is not None
        and user.is_authenticated
    ):
        from dashboard.selectors import dashboard_summary_get

        summary = dashboard_summary_get()
        context["nav_alerts"] = {
            "pending_leave": summary.pending_leave_count,
            "pending_overtime": summary.pending_overtime_count,
            "pending_corrections": summary.pending_correction_count,
            "missing_punch": summary.today_missing_punch_count,
        }

    return context
