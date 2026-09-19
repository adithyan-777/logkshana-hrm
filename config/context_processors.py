from django.urls import NoReverseMatch
from django_tenants.utils import get_public_schema_name

from config.navigation import (
    active_section,
    breadcrumbs_for,
    command_palette_for,
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
        "command_palette": [],
        "nav_can": {
            "dashboard": True,
            "employees": True,
            "leave": True,
            "schedule": True,
            "reports": True,
            "reports_self": True,
            "departments": True,
            "positions": True,
            "roles": True,
            "permissions": True,
            "attendance": True,
        },
        "attendance_nav_url": "",
    }

    try:
        context["topbar_action"] = topbar_action_for(request)
    except NoReverseMatch:
        context["topbar_action"] = None

    try:
        context["command_palette"] = command_palette_for(request)
    except NoReverseMatch:
        context["command_palette"] = []

    tenant = getattr(request, "tenant", None)
    user = getattr(request, "user", None)
    if (
        tenant is not None
        and getattr(tenant, "schema_name", None) != get_public_schema_name()
        and user is not None
        and user.is_authenticated
    ):
        from django.urls import reverse as reverse_url

        from employees.permission_catalog import PermissionCodename
        from employees.selectors import user_permission_codenames

        allowed = user_permission_codenames(user=user)

        def can(codename: str) -> bool:
            return allowed is None or codename in allowed

        context["nav_can"] = {
            "dashboard": can(PermissionCodename.DASHBOARD_VIEW),
            "employees": can(PermissionCodename.EMPLOYEES_VIEW),
            "leave": can(PermissionCodename.LEAVE_VIEW),
            "schedule": can(PermissionCodename.SCHEDULE_VIEW),
            "reports": can(PermissionCodename.REPORTS_VIEW),
            "reports_self": can(PermissionCodename.REPORTS_VIEW)
            or can(PermissionCodename.ATTENDANCE_OWN_VIEW),
            "departments": can(PermissionCodename.DEPARTMENTS_VIEW),
            "positions": can(PermissionCodename.POSITIONS_VIEW),
            "roles": can(PermissionCodename.ROLES_VIEW),
            "permissions": can(PermissionCodename.PERMISSIONS_VIEW),
            "attendance": can(PermissionCodename.ATTENDANCE_VIEW)
            or can(PermissionCodename.ATTENDANCE_OWN_VIEW),
        }
        if can(PermissionCodename.ATTENDANCE_VIEW):
            context["attendance_nav_url"] = reverse_url("attendance_transaction_list")
        elif can(PermissionCodename.ATTENDANCE_OWN_VIEW):
            context["attendance_nav_url"] = reverse_url("my_attendance")

        if can(PermissionCodename.DASHBOARD_VIEW):
            from dashboard.selectors import dashboard_summary_get

            summary = dashboard_summary_get()
            context["nav_alerts"] = {
                "pending_leave": summary.pending_leave_count,
                "pending_overtime": summary.pending_overtime_count,
                "pending_corrections": summary.pending_correction_count,
                "missing_punch": summary.today_missing_punch_count,
            }

    return context
