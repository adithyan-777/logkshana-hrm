from dataclasses import dataclass
from datetime import date

from django.db.models import Count, Q
from django.utils import timezone

from attendance.models import Attendance
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

    def attendance_chart_data(self) -> dict[str, list]:
        return {
            "labels": [
                "Present",
                "Absent",
                "Late",
                "On leave",
                "Incomplete",
                "Missing punch",
            ],
            "values": [
                self.today_present_count,
                self.today_absent_count,
                self.today_late_count,
                self.today_leave_count,
                self.today_incomplete_count,
                self.today_missing_punch_count,
            ],
        }


def dashboard_summary_get(*, target_date: date | None = None) -> DashboardSummary:
    if target_date is None:
        target_date = timezone.localdate()

    active_employee_count = Employee.objects.filter(is_active=True).count()

    today_stats = Attendance.objects.filter(day=target_date).aggregate(
        present_count=Count("id", filter=Q(status=Attendance.Status.PRESENT)),
        absent_count=Count("id", filter=Q(status=Attendance.Status.ABSENT)),
        late_count=Count("id", filter=Q(status=Attendance.Status.LATE)),
        leave_count=Count("id", filter=Q(status=Attendance.Status.LEAVE)),
        incomplete_count=Count(
            "id", filter=Q(status=Attendance.Status.INCOMPLETE)
        ),
        # No punch-direction flags are stored on the row: an incomplete
        # day is the "missing punch" signal.
        missing_punch_count=Count(
            "id", filter=Q(status=Attendance.Status.INCOMPLETE)
        ),
    )

    today_present_count = today_stats["present_count"] or 0
    if active_employee_count:
        present_percentage = round(
            (today_present_count / active_employee_count) * 100, 1
        )
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
        # No approval queues exist in the 2-model attendance flow.
        pending_overtime_count=0,
        pending_correction_count=0,
    )
