from datetime import date

from django.urls import reverse

from attendance.models import AttendanceCorrection, DailyAttendance, OvertimeRecord
from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    attendance_correction_factory,
    daily_attendance_factory,
    employee_factory,
    leave_request_factory,
)
from dashboard.selectors import dashboard_summary_get
from leave.models import LeaveRequest


class DashboardSummaryTests(BaseTenantTestCase):
    def test_calculates_today_kpis(self):
        employee = employee_factory(first_name="Dash", emp_code="D001")
        employee_factory(first_name="Inactive", emp_code="D002", is_active=False)
        daily_attendance_factory(
            employee=employee,
            date=date(2026, 2, 10),
            status=DailyAttendance.Status.PRESENT,
        )
        daily_attendance_factory(
            employee=employee_factory(first_name="Absent", emp_code="D003"),
            date=date(2026, 2, 10),
            status=DailyAttendance.Status.ABSENT,
        )
        leave_request_factory(employee=employee, status=LeaveRequest.Status.PENDING)

        summary = dashboard_summary_get(target_date=date(2026, 2, 10))

        self.assertEqual(summary.active_employee_count, 2)
        self.assertEqual(summary.today_present_count, 1)
        self.assertEqual(summary.today_absent_count, 1)
        self.assertEqual(summary.present_percentage, 50.0)
        self.assertEqual(summary.pending_leave_count, 1)

    def test_counts_pending_overtime_and_corrections(self):
        employee = employee_factory(first_name="Pending", emp_code="D004")
        daily = daily_attendance_factory(employee=employee, date=date(2026, 3, 1))
        OvertimeRecord.objects.create(
            employee=employee,
            date=date(2026, 3, 1),
            daily_attendance=daily,
            minutes=30,
            status=OvertimeRecord.Status.PENDING,
        )
        attendance_correction_factory(
            employee=employee,
            date=date(2026, 3, 1),
            status=AttendanceCorrection.Status.PENDING,
        )

        summary = dashboard_summary_get(target_date=date(2026, 3, 1))

        self.assertEqual(summary.pending_overtime_count, 1)
        self.assertEqual(summary.pending_correction_count, 1)


class DashboardViewTests(BaseTenantTestCase):
    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_returns_200_when_authenticated(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")
        self.assertContains(response, "Active Employees")
        self.assertContains(response, "Quick Actions")
        self.assertContains(response, "Review pending leave")
        self.assertContains(response, "Attendance exceptions")
        self.assertContains(response, "Logkshana")
        self.assertContains(response, "sidebar")
        self.assertContains(response, "sidebar-group")
        self.assertContains(response, "breadcrumbs")
