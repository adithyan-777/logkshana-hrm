from dataclasses import dataclass

from django.http import HttpRequest

ATTENDANCE_SUMMARY = "attendance_summary"
INDIVIDUAL_ATTENDANCE = "individual_attendance"
DEPARTMENT_ATTENDANCE = "department_attendance"


@dataclass(frozen=True)
class ReportColumn:
    key: str
    label: str


REPORT_COLUMNS: dict[str, list[ReportColumn]] = {
    ATTENDANCE_SUMMARY: [
        ReportColumn("employee_code", "Employee Code"),
        ReportColumn("employee", "Employee"),
        ReportColumn("department", "Department"),
        ReportColumn("total_days", "Total Days"),
        ReportColumn("present_days", "Present"),
        ReportColumn("absent_days", "Absent"),
        ReportColumn("late_days", "Late"),
        ReportColumn("leave_days", "Leave"),
        ReportColumn("worked", "Worked"),
        ReportColumn("late_minutes", "Late (min)"),
        ReportColumn("overtime_minutes", "OT (min)"),
    ],
    INDIVIDUAL_ATTENDANCE: [
        ReportColumn("date", "Date"),
        ReportColumn("status", "Status"),
        ReportColumn("expected_in", "Expected In"),
        ReportColumn("expected_out", "Expected Out"),
        ReportColumn("first_in", "First In"),
        ReportColumn("last_out", "Last Out"),
        ReportColumn("worked", "Worked"),
        ReportColumn("late", "Late"),
        ReportColumn("early_leave", "Early Leave"),
        ReportColumn("overtime", "OT"),
    ],
    DEPARTMENT_ATTENDANCE: [
        ReportColumn("department", "Department"),
        ReportColumn("employee_count", "Employees"),
        ReportColumn("total_days", "Total Days"),
        ReportColumn("present_days", "Present"),
        ReportColumn("absent_days", "Absent"),
        ReportColumn("late_days", "Late"),
        ReportColumn("late_minutes", "Late (min)"),
        ReportColumn("overtime_minutes", "OT (min)"),
    ],
}


def valid_column_keys(report_key: str) -> set[str]:
    return {column.key for column in REPORT_COLUMNS.get(report_key, [])}


def filter_columns(report_key: str, keys) -> list[ReportColumn]:
    """Return registry columns for `keys`, in registry order, dropping invalid keys."""
    requested = {key.strip() for key in keys if key and key.strip()}
    return [
        column
        for column in REPORT_COLUMNS.get(report_key, [])
        if column.key in requested
    ]


def all_columns(report_key: str) -> list[ReportColumn]:
    return list(REPORT_COLUMNS.get(report_key, []))


def resolve_report_columns(
    request: HttpRequest, *, report_key: str, preferred_keys: list[str] | None = None
) -> list[ReportColumn]:
    """URL `fields` param wins, then the user's saved preference, then all columns."""
    requested = request.GET.getlist("fields") if request else []
    if requested:
        keys = []
        for part in requested:
            keys.extend(part.split(","))
        columns = filter_columns(report_key, keys)
        if columns:
            return columns

    if preferred_keys:
        columns = filter_columns(report_key, preferred_keys)
        if columns:
            return columns

    return all_columns(report_key)
