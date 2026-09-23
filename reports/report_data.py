from reports.columns import ReportColumn
from reports.exports import ReportData
from reports.utils import format_datetime, format_minutes
from schedule.calculation import expected_datetimes


def duration_minutes(value) -> int | None:
    """Whole minutes in a DurationField value (None stays None)."""
    if value is None:
        return None
    return int(value.total_seconds() // 60)


def project_report_data(
    *, title: str, columns: list[ReportColumn], row_dicts: list[dict]
) -> ReportData:
    """Project full row dicts onto the selected columns for exports."""
    return ReportData(
        title=title,
        headers=[column.label for column in columns],
        rows=[[row[column.key] for column in columns] for row in row_dicts],
    )


def attendance_summary_row_dicts(rows) -> list[dict]:
    return [
        {
            "employee_code": row["employee__emp_code"] or "",
            "employee": f"{row['employee__first_name']} {row['employee__last_name']}".strip(),
            "department": row["employee__department__name"] or "",
            "total_days": row["total_days"],
            "present_days": row["present_days"],
            "absent_days": row["absent_days"],
            "late_days": row["late_days"],
            "leave_days": row["leave_days"],
            "worked": format_minutes(duration_minutes(row["total_worked"])),
            "late_minutes": duration_minutes(row["total_late"]) or 0,
            "overtime_minutes": duration_minutes(row["total_overtime"]) or 0,
        }
        for row in rows
    ]


def attendance_summary_report_data(rows, columns: list[ReportColumn]) -> ReportData:
    return project_report_data(
        title="Attendance Summary",
        columns=columns,
        row_dicts=attendance_summary_row_dicts(rows),
    )


def individual_attendance_row_dicts(records) -> list[dict]:
    dicts = []
    for record in records:
        if record.shift is not None:
            expected_in, expected_out = expected_datetimes(
                timetable=record.shift, day=record.day
            )
        else:
            expected_in, expected_out = None, None
        dicts.append(
            {
                "date": record.day,
                "status": record.get_status_display(),
                "status_code": record.status,
                "expected_in": format_datetime(expected_in),
                "expected_out": format_datetime(expected_out),
                "first_in": format_datetime(record.first_in),
                "last_out": format_datetime(record.last_out),
                "worked": format_minutes(duration_minutes(record.total_work_time)),
                "late": format_minutes(duration_minutes(record.late_time)),
                "early_leave": format_minutes(
                    duration_minutes(record.early_leave_time)
                ),
                "overtime": format_minutes(duration_minutes(record.over_time)),
            }
        )
    return dicts


def individual_attendance_report_data(
    records, columns: list[ReportColumn]
) -> ReportData:
    return project_report_data(
        title="Individual Attendance",
        columns=columns,
        row_dicts=individual_attendance_row_dicts(records),
    )


def department_attendance_row_dicts(rows) -> list[dict]:
    return [
        {
            "department": row["employee__department__name"] or "Unassigned",
            "employee_count": row["employee_count"],
            "total_days": row["total_days"],
            "present_days": row["present_days"],
            "absent_days": row["absent_days"],
            "late_days": row["late_days"],
            "late_minutes": duration_minutes(row["total_late"]) or 0,
            "overtime_minutes": duration_minutes(row["total_overtime"]) or 0,
        }
        for row in rows
    ]


def department_attendance_report_data(rows, columns: list[ReportColumn]) -> ReportData:
    return project_report_data(
        title="Department Attendance",
        columns=columns,
        row_dicts=department_attendance_row_dicts(rows),
    )


def exception_report_data(records) -> ReportData:
    return ReportData(
        title="Attendance Exceptions",
        headers=[
            "Date",
            "Employee",
            "Department",
            "Status",
            "Check In",
            "Check Out",
            "Late (min)",
            "Shift",
        ],
        rows=[
            [
                record.day,
                record.employee.full_name,
                record.employee.department.name if record.employee.department else "",
                record.get_status_display(),
                "Yes" if record.has_check_in else "No",
                "Yes" if record.has_check_out else "No",
                record.late_minutes,
                record.shift.name if record.shift else "—",
            ]
            for record in records
        ],
    )


def punch_log_report_data(activities) -> ReportData:
    return ReportData(
        title="Punch Log",
        headers=[
            "Timestamp",
            "Employee",
            "Department",
            "Direction",
            "Source",
            "External ID",
        ],
        rows=[
            [
                format_datetime(activity.punch_time),
                activity.employee.full_name,
                activity.employee.department.name
                if activity.employee.department
                else "",
                activity.get_direction_display(),
                activity.get_method_display(),
                activity.external_id,
            ]
            for activity in activities
        ],
    )


def overtime_report_data(records) -> ReportData:
    return ReportData(
        title="Overtime Summary",
        headers=[
            "Date",
            "Employee",
            "Department",
            "Minutes",
            "Status",
            "Shift",
        ],
        rows=[
            [
                record.day,
                record.employee.full_name,
                record.employee.department.name if record.employee.department else "",
                record.overtime_minutes,
                record.get_status_display(),
                record.shift.name if record.shift else "—",
            ]
            for record in records
        ],
    )


def leave_balance_report_data(balances) -> ReportData:
    return ReportData(
        title="Leave Balance",
        headers=[
            "Employee",
            "Department",
            "Leave Type",
            "Year",
            "Entitled",
            "Carried",
            "Adjustment",
            "Used",
            "Pending",
            "Available",
        ],
        rows=[
            [
                balance.employee.full_name,
                balance.employee.department.name if balance.employee.department else "",
                balance.leave_type.name,
                balance.year,
                balance.entitled_days,
                balance.carried_forward_days,
                balance.adjustment_days,
                balance.used_days,
                balance.pending_days,
                balance.available_days,
            ]
            for balance in balances
        ],
    )


def leave_utilization_report_data(requests) -> ReportData:
    return ReportData(
        title="Leave Utilization",
        headers=[
            "Employee",
            "Department",
            "Leave Type",
            "Start",
            "End",
            "Days",
            "Reason",
        ],
        rows=[
            [
                leave_request.employee.full_name,
                leave_request.employee.department.name
                if leave_request.employee.department
                else "",
                leave_request.leave_type.name,
                leave_request.start_date,
                leave_request.end_date,
                leave_request.days,
                leave_request.reason,
            ]
            for leave_request in requests
        ],
    )


def pending_leave_report_data(requests) -> ReportData:
    return ReportData(
        title="Pending Leave",
        headers=[
            "Employee",
            "Department",
            "Leave Type",
            "Start",
            "End",
            "Days",
            "Reason",
        ],
        rows=[
            [
                leave_request.employee.full_name,
                leave_request.employee.department.name
                if leave_request.employee.department
                else "",
                leave_request.leave_type.name,
                leave_request.start_date,
                leave_request.end_date,
                leave_request.days,
                leave_request.reason,
            ]
            for leave_request in requests
        ],
    )
