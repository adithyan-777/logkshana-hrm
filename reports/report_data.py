from reports.exports import ReportData
from reports.utils import format_datetime, format_minutes


def attendance_summary_report_data(rows) -> ReportData:
    return ReportData(
        title="Attendance Summary",
        headers=[
            "Employee Code",
            "Employee",
            "Department",
            "Total Days",
            "Present",
            "Absent",
            "Late",
            "Leave",
            "Worked",
            "Late (min)",
            "OT (min)",
        ],
        rows=[
            [
                row["employee__emp_code"] or "",
                f"{row['employee__first_name']} {row['employee__last_name']}".strip(),
                row["employee__department__name"] or "",
                row["total_days"],
                row["present_days"],
                row["absent_days"],
                row["late_days"],
                row["leave_days"],
                format_minutes(row["total_worked_minutes"]),
                row["total_late_minutes"] or 0,
                row["total_overtime_minutes"] or 0,
            ]
            for row in rows
        ],
    )


def individual_attendance_report_data(records) -> ReportData:
    return ReportData(
        title="Individual Attendance",
        headers=[
            "Date",
            "Status",
            "Expected In",
            "Expected Out",
            "First In",
            "Last Out",
            "Worked",
            "Late",
            "Early Leave",
            "OT",
        ],
        rows=[
            [
                record.date,
                record.get_status_display(),
                format_datetime(record.expected_in),
                format_datetime(record.expected_out),
                format_datetime(record.first_in),
                format_datetime(record.last_out),
                format_minutes(record.worked_minutes),
                format_minutes(record.late_minutes),
                format_minutes(record.early_leave_minutes),
                format_minutes(record.overtime_minutes),
            ]
            for record in records
        ],
    )


def department_attendance_report_data(rows) -> ReportData:
    return ReportData(
        title="Department Attendance",
        headers=[
            "Department",
            "Employees",
            "Total Days",
            "Present",
            "Absent",
            "Late",
            "Late (min)",
            "OT (min)",
        ],
        rows=[
            [
                row["employee__department__name"] or "Unassigned",
                row["employee_count"],
                row["total_days"],
                row["present_days"],
                row["absent_days"],
                row["late_days"],
                row["total_late_minutes"] or 0,
                row["total_overtime_minutes"] or 0,
            ]
            for row in rows
        ],
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
            "Notes",
        ],
        rows=[
            [
                record.date,
                record.employee.full_name,
                record.employee.department.name if record.employee.department else "",
                record.get_status_display(),
                "Yes" if record.has_check_in else "No",
                "Yes" if record.has_check_out else "No",
                record.late_minutes,
                record.notes,
            ]
            for record in records
        ],
    )


def punch_log_report_data(transactions) -> ReportData:
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
                format_datetime(transaction.timestamp),
                transaction.employee.full_name,
                transaction.employee.department.name if transaction.employee.department else "",
                transaction.get_direction_display(),
                transaction.get_source_display(),
                transaction.external_id,
            ]
            for transaction in transactions
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
            "Reason",
        ],
        rows=[
            [
                record.date,
                record.employee.full_name,
                record.employee.department.name if record.employee.department else "",
                record.minutes,
                record.get_status_display(),
                record.reason,
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
