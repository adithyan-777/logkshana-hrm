from django.db import OperationalError, ProgrammingError
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


def _leave_nav_hidden() -> bool:
    """Current tenant turned its Leave nav off via a waffle Switch row.

    Read waffle directly through the tenant connection instead of waffle's
    cached lookups (`switch_is_active` / ``{% switch %}``) — those cache
    keys are not schema-prefixed and leak values across tenants in one
    process. Missing row, or unmigrated schema, means "shown" (fail open).
    """
    from waffle.models import Switch

    try:
        switch = Switch.objects.get(name="hide_leave")
    except (Switch.DoesNotExist, OperationalError, ProgrammingError):
        return False
    return switch.active


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
            "devices": True,
            "branches": True,
            "settings": True,
        },
        "attendance_nav_url": "",
    }

    # Sidebar "Organization" group auto-opens on any of its pages.
    context["nav_org_open"] = request.path.startswith(
        (
            "/employees/departments/",
            "/employees/positions/",
            "/employees/roles/",
            "/employees/permissions/",
            "/devices/",
        )
    )

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

        leave_nav_hidden = _leave_nav_hidden()

        context["nav_can"] = {
            "dashboard": can(PermissionCodename.DASHBOARD_VIEW),
            "employees": can(PermissionCodename.EMPLOYEES_VIEW),
            "leave": can(PermissionCodename.LEAVE_VIEW) and not leave_nav_hidden,
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
            "devices": can(PermissionCodename.DEVICES_VIEW),
            "branches": can(PermissionCodename.BRANCHES_VIEW),
            "settings": True,
        }
        if can(PermissionCodename.ATTENDANCE_VIEW):
            context["attendance_nav_url"] = reverse_url("daily_attendance_list")
        elif can(PermissionCodename.ATTENDANCE_OWN_VIEW):
            context["attendance_nav_url"] = reverse_url("my_attendance")

        if can(PermissionCodename.DASHBOARD_VIEW):
            from dashboard.selectors import dashboard_summary_get

            summary = dashboard_summary_get()
            context["nav_alerts"] = {
                # Leave hidden for this tenant (waffle switch): also drop
                # the "pending leave" notifications-menu entry.
                "pending_leave": 0 if leave_nav_hidden else summary.pending_leave_count,
                "pending_overtime": summary.pending_overtime_count,
                "pending_corrections": summary.pending_correction_count,
                "missing_punch": summary.today_missing_punch_count,
            }

    return context
