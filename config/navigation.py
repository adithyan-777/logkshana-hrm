from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse

SECTIONS = {
    "leave": "/leave/",
    "schedule": "/schedule/",
    "reports": "/reports/",
}

BREADCRUMBS: dict[str, list[tuple[str, str | None]]] = {
    "dashboard": [("Dashboard", None)],
    "account_profile": [("Dashboard", "dashboard"), ("Profile", None)],
    "employee_list": [("Dashboard", "dashboard"), ("Employees", None)],
    "employee_add": [
        ("Dashboard", "dashboard"),
        ("Employees", "employee_list"),
        ("Add employee", None),
    ],
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


PAGE_HEADINGS: dict[str, str] = {
    "dashboard": "Dashboard",
    "account_profile": "Profile",
    "employee_list": "Employees",
    "employee_add": "Add Employee",
    "attendance_transaction_list": "Attendance",
    "attendance_transaction_add": "Record Punch",
    "daily_attendance_list": "Attendance",
    "daily_attendance_add": "Add Daily Record",
    "attendance_correction_list": "Attendance",
    "attendance_correction_add": "Submit Correction",
    "attendance_rule_list": "Attendance",
    "attendance_rule_add": "Add Rule",
    "leave_type_list": "Leave",
    "leave_type_add": "Add Leave Type",
    "leave_policy_list": "Leave",
    "leave_policy_add": "Add Leave Policy",
    "leave_request_list": "Leave",
    "leave_request_add": "Add Leave Request",
    "holiday_list": "Leave",
    "holiday_add": "Add Holiday",
    "timetable_list": "Schedule",
    "timetable_add": "Add Timetable",
    "shift_list": "Schedule",
    "shift_add": "Add Shift",
    "assignment_list": "Schedule",
    "assignment_add": "Add Assignment",
    "temporary_list": "Schedule",
    "temporary_add": "Add Temporary Schedule",
    "report_hub": "Reports",
    "report_attendance_summary": "Reports",
    "report_individual_attendance": "Reports",
    "report_department_attendance": "Reports",
    "report_exceptions": "Reports",
    "report_punch_log": "Reports",
    "report_overtime": "Reports",
    "report_leave": "Reports",
}

PAGE_SUBTITLES: dict[str, str] = {
    "account_profile": "Read-only account details.",
    "employee_list": "Directory + active/inactive status.",
    "employee_add": "Create an employee and send a password-setup invite.",
    "attendance_transaction_list": "Punches, daily outcomes, corrections, and rules.",
    "daily_attendance_list": "Punches, daily outcomes, corrections, and rules.",
    "attendance_correction_list": "Punches, daily outcomes, corrections, and rules.",
    "attendance_rule_list": "Punches, daily outcomes, corrections, and rules.",
    "attendance_transaction_add": "Record a check-in or check-out.",
    "daily_attendance_add": "Add a calculated daily attendance row.",
    "attendance_correction_add": "Submit a punch correction for review.",
    "attendance_rule_add": "Configure how attendance is calculated.",
    "leave_type_list": "Types, policies, requests, and holidays.",
    "leave_policy_list": "Types, policies, requests, and holidays.",
    "leave_request_list": "Types, policies, requests, and holidays.",
    "holiday_list": "Types, policies, requests, and holidays.",
    "leave_type_add": "Add a leave category.",
    "leave_policy_add": "Add entitlement and accrual rules.",
    "leave_request_add": "Create a leave request.",
    "holiday_add": "Add a company holiday.",
    "timetable_list": "Timetables, shifts, assignments, and temporary overrides.",
    "shift_list": "Timetables, shifts, assignments, and temporary overrides.",
    "assignment_list": "Timetables, shifts, assignments, and temporary overrides.",
    "temporary_list": "Timetables, shifts, assignments, and temporary overrides.",
    "timetable_add": "Define check-in and check-out times.",
    "shift_add": "Build a named rotation of timetables.",
    "assignment_add": "Apply a shift to people or departments.",
    "temporary_add": "Override one employee for one date.",
    "report_hub": "Filtered analytics with CSV, Excel, and PDF export.",
    "report_attendance_summary": "Filtered analytics with CSV, Excel, and PDF export.",
    "report_individual_attendance": "Filtered analytics with CSV, Excel, and PDF export.",
    "report_department_attendance": "Filtered analytics with CSV, Excel, and PDF export.",
    "report_exceptions": "Filtered analytics with CSV, Excel, and PDF export.",
    "report_punch_log": "Filtered analytics with CSV, Excel, and PDF export.",
    "report_overtime": "Filtered analytics with CSV, Excel, and PDF export.",
    "report_leave": "Filtered analytics with CSV, Excel, and PDF export.",
}


COMMAND_PALETTE: list[dict[str, str]] = [
    {
        "title": "Dashboard",
        "subtitle": "Today’s attendance pulse",
        "url_name": "dashboard",
        "group": "Overview",
        "icon": "bx-grid",
    },
    {
        "title": "Employees",
        "subtitle": "Company directory",
        "url_name": "employee_list",
        "group": "People",
        "icon": "bx-user",
    },
    {
        "title": "Add employee",
        "subtitle": "Create a staff record",
        "url_name": "employee_add",
        "group": "People",
        "icon": "bx-user-plus",
    },
    {
        "title": "Punches",
        "subtitle": "Raw check-in and check-out",
        "url_name": "attendance_transaction_list",
        "group": "Attendance",
        "icon": "bx-walk",
    },
    {
        "title": "Record punch",
        "subtitle": "Log a check-in or check-out",
        "url_name": "attendance_transaction_add",
        "group": "Attendance",
        "icon": "bx-plus",
    },
    {
        "title": "Daily attendance",
        "subtitle": "Calculated day outcomes",
        "url_name": "daily_attendance_list",
        "group": "Attendance",
        "icon": "bx-calendar-check",
    },
    {
        "title": "Corrections",
        "subtitle": "Punch fixes awaiting review",
        "url_name": "attendance_correction_list",
        "group": "Attendance",
        "icon": "bx-edit",
    },
    {
        "title": "Attendance rules",
        "subtitle": "Grace periods and calculation",
        "url_name": "attendance_rule_list",
        "group": "Attendance",
        "icon": "bx-slider",
    },
    {
        "title": "Leave requests",
        "subtitle": "Time-off awaiting a decision",
        "url_name": "leave_request_list",
        "group": "Leave",
        "icon": "bx-calendar-minus",
    },
    {
        "title": "Add leave request",
        "subtitle": "Create a leave request",
        "url_name": "leave_request_add",
        "group": "Leave",
        "icon": "bx-plus",
    },
    {
        "title": "Leave types",
        "subtitle": "Paid, unpaid, and categories",
        "url_name": "leave_type_list",
        "group": "Leave",
        "icon": "bx-category",
    },
    {
        "title": "Leave policies",
        "subtitle": "Entitlement and accrual",
        "url_name": "leave_policy_list",
        "group": "Leave",
        "icon": "bx-shield",
    },
    {
        "title": "Holidays",
        "subtitle": "Company calendar",
        "url_name": "holiday_list",
        "group": "Leave",
        "icon": "bx-party",
    },
    {
        "title": "Timetables",
        "subtitle": "Check-in and check-out times",
        "url_name": "timetable_list",
        "group": "Schedule",
        "icon": "bx-clock-5",
    },
    {
        "title": "Shifts",
        "subtitle": "Named rotations",
        "url_name": "shift_list",
        "group": "Schedule",
        "icon": "bx-repeat",
    },
    {
        "title": "Assignments",
        "subtitle": "Who works which shift",
        "url_name": "assignment_list",
        "group": "Schedule",
        "icon": "bx-user-circle",
    },
    {
        "title": "Temporary schedule",
        "subtitle": "One-off overrides",
        "url_name": "temporary_list",
        "group": "Schedule",
        "icon": "bx-calendar-exclamation",
    },
    {
        "title": "Reports",
        "subtitle": "Analytics hub",
        "url_name": "report_hub",
        "group": "Reports",
        "icon": "bx-chart-bar-columns",
    },
    {
        "title": "Attendance summary",
        "subtitle": "Totals per employee",
        "url_name": "report_attendance_summary",
        "group": "Reports",
        "icon": "bx-bar-chart",
    },
    {
        "title": "Individual attendance",
        "subtitle": "Day-by-day for one person",
        "url_name": "report_individual_attendance",
        "group": "Reports",
        "icon": "bx-id-card",
    },
    {
        "title": "Department attendance",
        "subtitle": "Aggregated by department",
        "url_name": "report_department_attendance",
        "group": "Reports",
        "icon": "bx-buildings",
    },
    {
        "title": "Exceptions",
        "subtitle": "Late, absent, missing punch",
        "url_name": "report_exceptions",
        "group": "Reports",
        "icon": "bx-error-circle",
    },
    {
        "title": "Punch log",
        "subtitle": "Raw punch stream",
        "url_name": "report_punch_log",
        "group": "Reports",
        "icon": "bx-list-ul",
    },
    {
        "title": "Overtime",
        "subtitle": "Overtime minutes and status",
        "url_name": "report_overtime",
        "group": "Reports",
        "icon": "bx-time-five",
    },
    {
        "title": "Leave reports",
        "subtitle": "Balance and utilization",
        "url_name": "report_leave",
        "group": "Reports",
        "icon": "bx-calendar",
    },
    {
        "title": "Profile",
        "subtitle": "Account details",
        "url_name": "account_profile",
        "group": "Account",
        "icon": "bx-user",
    },
]


def _url_name(request: HttpRequest) -> str | None:
    return getattr(getattr(request, "resolver_match", None), "url_name", None)


def page_heading_for(request: HttpRequest) -> str:
    url_name = _url_name(request)
    if url_name and url_name in PAGE_HEADINGS:
        return PAGE_HEADINGS[url_name]
    crumbs = breadcrumbs_for(request)
    if crumbs:
        return crumbs[-1][0]
    return "Dashboard"


def page_subtitle_for(request: HttpRequest) -> str:
    url_name = _url_name(request)
    if not url_name:
        return ""
    return PAGE_SUBTITLES.get(url_name, "")


def topbar_action_for(request: HttpRequest) -> dict[str, str] | None:
    action = page_action_for(request)
    if not action:
        return None
    label, url_name = action
    return {"label": label, "url": reverse(url_name)}


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


def command_palette_for(_request: HttpRequest) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for entry in COMMAND_PALETTE:
        try:
            url = reverse(entry["url_name"])
        except NoReverseMatch:
            continue
        items.append({**entry, "url": url})
    return items
