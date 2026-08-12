from dataclasses import dataclass
from datetime import date

from django.db.models import Count, Q
from django.utils import timezone

from attendance.models import AttendanceCorrection, DailyAttendance, OvertimeRecord
from employees.models import Employee
from leave.models import LeaveRequest


@dataclass(frozen=True)
class DashboardSummary:
    target_date: date
    active_employee_count: int
    today_present_count: int
    today_absent_count: int
    today_late_count: int
    today_leave_count: int
    today_incomplete_count: int
    today_missing_punch_count: int
    present_percentage: float
    pending_leave_count: int
    pending_overtime_count: int
    pending_correction_count: int


def dashboard_summary_get(*, target_date: date | None = None) -> DashboardSummary:
    if target_date is None:
        target_date = timezone.localdate()

    active_employee_count = Employee.objects.filter(is_active=True).count()

    today_stats = DailyAttendance.objects.filter(date=target_date).aggregate(
        present_count=Count("id", filter=Q(status=DailyAttendance.Status.PRESENT)),
        absent_count=Count("id", filter=Q(status=DailyAttendance.Status.ABSENT)),
        late_count=Count("id", filter=Q(status=DailyAttendance.Status.LATE)),
        leave_count=Count("id", filter=Q(status=DailyAttendance.Status.LEAVE)),
        incomplete_count=Count("id", filter=Q(status=DailyAttendance.Status.INCOMPLETE)),
        missing_punch_count=Count(
            "id",
            filter=Q(has_check_in=False) | Q(has_check_out=False),
        ),
    )

    today_present_count = today_stats["present_count"] or 0
    if active_employee_count:
        present_percentage = round((today_present_count / active_employee_count) * 100, 1)
    else:
        present_percentage = 0.0

    return DashboardSummary(
        target_date=target_date,
        active_employee_count=active_employee_count,
        today_present_count=today_present_count,
        today_absent_count=today_stats["absent_count"] or 0,
        today_late_count=today_stats["late_count"] or 0,
        today_leave_count=today_stats["leave_count"] or 0,
        today_incomplete_count=today_stats["incomplete_count"] or 0,
        today_missing_punch_count=today_stats["missing_punch_count"] or 0,
        present_percentage=present_percentage,
        pending_leave_count=LeaveRequest.objects.filter(
            status=LeaveRequest.Status.PENDING,
        ).count(),
        pending_overtime_count=OvertimeRecord.objects.filter(
            status=OvertimeRecord.Status.PENDING,
        ).count(),
        pending_correction_count=AttendanceCorrection.objects.filter(
            status=AttendanceCorrection.Status.PENDING,
        ).count(),
    )
