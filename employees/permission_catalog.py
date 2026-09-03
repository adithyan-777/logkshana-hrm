from django.db import models


class PermissionCodename(models.TextChoices):
    DASHBOARD_VIEW = "dashboard.view", "View dashboard"
    EMPLOYEES_VIEW = "employees.view", "View employees"
    EMPLOYEES_ADD = "employees.add", "Add employees"
    EMPLOYEES_EDIT = "employees.edit", "Edit employees"
    DEPARTMENTS_VIEW = "departments.view", "View departments"
    DEPARTMENTS_ADD = "departments.add", "Add departments"
    POSITIONS_VIEW = "positions.view", "View positions"
    POSITIONS_ADD = "positions.add", "Add positions"
    ROLES_VIEW = "roles.view", "View roles"
    ROLES_ADD = "roles.add", "Add roles"
    PERMISSIONS_VIEW = "permissions.view", "View permissions"
    PERMISSIONS_ADD = "permissions.add", "Add permissions"
    ATTENDANCE_VIEW = "attendance.view", "View attendance"
    ATTENDANCE_OWN_VIEW = "attendance.own.view", "View own attendance"
    ATTENDANCE_ADD = "attendance.add", "Record punches"
    ATTENDANCE_CORRECT = "attendance.correct", "Correct attendance"
    ATTENDANCE_RULES_MANAGE = "attendance.rules.manage", "Manage attendance rules"
    LEAVE_VIEW = "leave.view", "View leave"
    LEAVE_ADD = "leave.add", "Add leave requests"
    LEAVE_APPROVE = "leave.approve", "Approve leave"
    LEAVE_TYPES_MANAGE = "leave.types.manage", "Manage leave types"
    LEAVE_HOLIDAYS_MANAGE = "leave.holidays.manage", "Manage holidays"
    SCHEDULE_VIEW = "schedule.view", "View schedule"
    SCHEDULE_ADD = "schedule.add", "Add schedules"
    REPORTS_VIEW = "reports.view", "View reports"


_DESCRIPTIONS: dict[str, str] = {
    PermissionCodename.DASHBOARD_VIEW: "Open the company dashboard.",
    PermissionCodename.EMPLOYEES_VIEW: "View the employee directory.",
    PermissionCodename.EMPLOYEES_ADD: "Create employees and send invites.",
    PermissionCodename.EMPLOYEES_EDIT: "Update employee records.",
    PermissionCodename.DEPARTMENTS_VIEW: "View departments.",
    PermissionCodename.DEPARTMENTS_ADD: "Create departments.",
    PermissionCodename.POSITIONS_VIEW: "View positions.",
    PermissionCodename.POSITIONS_ADD: "Create positions.",
    PermissionCodename.ROLES_VIEW: "View roles.",
    PermissionCodename.ROLES_ADD: "Create roles.",
    PermissionCodename.PERMISSIONS_VIEW: "View permissions.",
    PermissionCodename.PERMISSIONS_ADD: "Create permissions.",
    PermissionCodename.ATTENDANCE_VIEW: "View punches and daily attendance.",
    PermissionCodename.ATTENDANCE_OWN_VIEW: "View your own punches and daily attendance.",
    PermissionCodename.ATTENDANCE_ADD: "Record check-in and check-out punches.",
    PermissionCodename.ATTENDANCE_CORRECT: "Submit and review attendance corrections.",
    PermissionCodename.ATTENDANCE_RULES_MANAGE: "Configure attendance calculation rules.",
    PermissionCodename.LEAVE_VIEW: "View leave requests.",
    PermissionCodename.LEAVE_ADD: "Create leave requests.",
    PermissionCodename.LEAVE_APPROVE: "Approve or reject leave requests.",
    PermissionCodename.LEAVE_TYPES_MANAGE: "Manage leave types and policies.",
    PermissionCodename.LEAVE_HOLIDAYS_MANAGE: "Manage company holidays.",
    PermissionCodename.SCHEDULE_VIEW: "View timetables, shifts, and assignments.",
    PermissionCodename.SCHEDULE_ADD: "Create timetables, shifts, and assignments.",
    PermissionCodename.REPORTS_VIEW: "Open reports and analytics.",
}


EMPLOYEE_ROLE_NAME = "Employee"


PERMISSION_MODULE_LABELS: dict[str, str] = {
    "dashboard": "Dashboard",
    "employees": "Employees",
    "departments": "Departments",
    "positions": "Positions",
    "roles": "Roles",
    "permissions": "Permissions",
    "attendance": "Attendance",
    "leave": "Leave",
    "schedule": "Schedule",
    "reports": "Reports",
}


def permission_catalog_entries() -> list[dict[str, str]]:
    return [
        {
            "codename": value,
            "name": PermissionCodename(value).label,
            "description": _DESCRIPTIONS.get(value, ""),
        }
        for value in PermissionCodename.values
    ]


def permission_module_key(codename: str) -> str:
    if not codename or "." not in codename:
        return ""
    return codename.split(".", 1)[0]


def permission_module_label(codename: str) -> str:
    key = permission_module_key(codename)
    return PERMISSION_MODULE_LABELS.get(key, "Other")


def permissions_grouped_choices(permissions) -> list[tuple[str, list[tuple[int, str]]]]:
    grouped: dict[str, list[tuple[int, str]]] = {}
    for permission in permissions:
        label = permission_module_label(permission.codename)
        grouped.setdefault(label, []).append((permission.pk, permission.name))

    ordered: list[tuple[str, list[tuple[int, str]]]] = []
    for label in PERMISSION_MODULE_LABELS.values():
        if label in grouped:
            ordered.append((label, grouped.pop(label)))
    if "Other" in grouped:
        ordered.append(("Other", grouped.pop("Other")))
    return ordered
