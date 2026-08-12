from django.http import HttpRequest

SECTIONS = {
    "leave": "/leave/",
    "schedule": "/schedule/",
    "reports": "/reports/",
}

BREADCRUMBS: dict[str, list[tuple[str, str | None]]] = {
    "dashboard": [("Dashboard", None)],
    "account_profile": [("Dashboard", "dashboard"), ("Profile", None)],
    "employee_list": [("Dashboard", "dashboard"), ("Employees", None)],
    "employee_add": [("Dashboard", "dashboard"), ("Employees", "employee_list"), ("Add employee", None)],
    "attendance_transaction_list": [
        ("Dashboard", "dashboard"),
        ("Attendance", None),
        ("Punches", None),
    ],
    "attendance_transaction_add": [
        ("Dashboard", "dashboard"),
        ("Attendance", None),
        ("Punches", "attendance_transaction_list"),
        ("Record punch", None),
    ],
    "daily_attendance_list": [
        ("Dashboard", "dashboard"),
        ("Attendance", None),
        ("Daily", None),
    ],
    "daily_attendance_add": [
        ("Dashboard", "dashboard"),
        ("Attendance", None),
        ("Daily", "daily_attendance_list"),
        ("Add daily record", None),
    ],
    "attendance_correction_list": [
        ("Dashboard", "dashboard"),
        ("Attendance", None),
        ("Corrections", None),
    ],
    "attendance_correction_add": [
        ("Dashboard", "dashboard"),
        ("Attendance", None),
        ("Corrections", "attendance_correction_list"),
        ("Submit correction", None),
    ],
    "attendance_rule_list": [
        ("Dashboard", "dashboard"),
        ("Attendance", None),
        ("Rules", None),
    ],
    "attendance_rule_add": [
        ("Dashboard", "dashboard"),
        ("Attendance", None),
        ("Rules", "attendance_rule_list"),
        ("Add rule", None),
    ],
    "leave_type_list": [
        ("Dashboard", "dashboard"),
        ("Leave", None),
        ("Types", None),
    ],
    "leave_type_add": [
        ("Dashboard", "dashboard"),
        ("Leave", None),
        ("Types", "leave_type_list"),
        ("Add leave type", None),
    ],
    "leave_policy_list": [
        ("Dashboard", "dashboard"),
        ("Leave", None),
        ("Policies", None),
    ],
    "leave_policy_add": [
        ("Dashboard", "dashboard"),
        ("Leave", None),
        ("Policies", "leave_policy_list"),
        ("Add leave policy", None),
    ],
    "leave_request_list": [
        ("Dashboard", "dashboard"),
        ("Leave", None),
        ("Requests", None),
    ],
    "leave_request_add": [
        ("Dashboard", "dashboard"),
        ("Leave", None),
        ("Requests", "leave_request_list"),
        ("Add leave request", None),
    ],
    "holiday_list": [
        ("Dashboard", "dashboard"),
        ("Leave", None),
        ("Holidays", None),
    ],
    "holiday_add": [
        ("Dashboard", "dashboard"),
        ("Leave", None),
        ("Holidays", "holiday_list"),
        ("Add holiday", None),
    ],
    "timetable_list": [
        ("Dashboard", "dashboard"),
        ("Schedule", None),
        ("Timetables", None),
    ],
    "timetable_add": [
        ("Dashboard", "dashboard"),
        ("Schedule", None),
        ("Timetables", "timetable_list"),
        ("Add timetable", None),
    ],
    "shift_list": [
        ("Dashboard", "dashboard"),
        ("Schedule", None),
        ("Shifts", None),
    ],
    "shift_add": [
        ("Dashboard", "dashboard"),
        ("Schedule", None),
        ("Shifts", "shift_list"),
        ("Add shift", None),
    ],
    "assignment_list": [
        ("Dashboard", "dashboard"),
        ("Schedule", None),
        ("Assignments", None),
    ],
    "assignment_add": [
        ("Dashboard", "dashboard"),
        ("Schedule", None),
        ("Assignments", "assignment_list"),
        ("Add assignment", None),
    ],
    "temporary_list": [
        ("Dashboard", "dashboard"),
        ("Schedule", None),
        ("Temporary", None),
    ],
    "temporary_add": [
        ("Dashboard", "dashboard"),
        ("Schedule", None),
        ("Temporary", "temporary_list"),
        ("Add temporary schedule", None),
    ],
    "report_hub": [("Dashboard", "dashboard"), ("Reports", None)],
    "report_attendance_summary": [
        ("Dashboard", "dashboard"),
        ("Reports", "report_hub"),
        ("Attendance summary", None),
    ],
    "report_individual_attendance": [
        ("Dashboard", "dashboard"),
        ("Reports", "report_hub"),
        ("Individual attendance", None),
    ],
    "report_department_attendance": [
        ("Dashboard", "dashboard"),
        ("Reports", "report_hub"),
        ("Department attendance", None),
    ],
    "report_exceptions": [
        ("Dashboard", "dashboard"),
        ("Reports", "report_hub"),
        ("Exceptions", None),
    ],
    "report_punch_log": [
        ("Dashboard", "dashboard"),
        ("Reports", "report_hub"),
        ("Punch log", None),
    ],
    "report_overtime": [
        ("Dashboard", "dashboard"),
        ("Reports", "report_hub"),
        ("Overtime", None),
    ],
    "report_leave": [
        ("Dashboard", "dashboard"),
        ("Reports", "report_hub"),
        ("Leave reports", None),
    ],
}

LIST_ACTIONS: dict[str, tuple[str, str]] = {
    "employee_list": ("Add employee", "employee_add"),
    "attendance_transaction_list": ("Record punch", "attendance_transaction_add"),
    "daily_attendance_list": ("Add daily record", "daily_attendance_add"),
    "attendance_correction_list": ("Submit correction", "attendance_correction_add"),
    "attendance_rule_list": ("Add rule", "attendance_rule_add"),
    "leave_type_list": ("Add leave type", "leave_type_add"),
    "leave_policy_list": ("Add leave policy", "leave_policy_add"),
    "leave_request_list": ("Add leave request", "leave_request_add"),
    "holiday_list": ("Add holiday", "holiday_add"),
    "timetable_list": ("Add timetable", "timetable_add"),
    "shift_list": ("Add shift", "shift_add"),
    "assignment_list": ("Add assignment", "assignment_add"),
    "temporary_list": ("Add temporary schedule", "temporary_add"),
}


def active_section(request: HttpRequest) -> str | None:
    path = request.path
    for section, prefix in SECTIONS.items():
        if path.startswith(prefix):
            return section
    return None


def breadcrumbs_for(request: HttpRequest) -> list[tuple[str, str | None]]:
    url_name = getattr(getattr(request, "resolver_match", None), "url_name", None)
    if not url_name:
        return []
    return BREADCRUMBS.get(url_name, [])


def page_action_for(request: HttpRequest) -> tuple[str, str] | None:
    url_name = getattr(getattr(request, "resolver_match", None), "url_name", None)
    if not url_name:
        return None
    return LIST_ACTIONS.get(url_name)
