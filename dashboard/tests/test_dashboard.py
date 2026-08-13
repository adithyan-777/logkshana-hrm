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

    def test_attendance_chart_data(self):
        summary = dashboard_summary_get(target_date=date(2026, 2, 10))

        chart_data = summary.attendance_chart_data()

        self.assertEqual(
            chart_data["labels"],
            [
                "Present",
                "Absent",
                "Late",
                "On leave",
                "Incomplete",
                "Missing punch",
            ],
        )
        self.assertEqual(len(chart_data["values"]), 6)


class DashboardViewTests(BaseTenantTestCase):
    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_returns_200_when_authenticated(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")
        self.assertContains(response, "Active employees")
        self.assertContains(response, "Quick actions")
        self.assertContains(response, "Leave requests")
        self.assertContains(response, "Exceptions")
        self.assertContains(response, "Logkshana")
        self.assertContains(response, "sidebar")
        self.assertContains(response, "breadcrumbs")
        self.assertContains(response, 'id="attendance-chart"')
        self.assertContains(response, 'id="attendance-chart-panel"')
        self.assertContains(response, 'id="attendance-chart-data"')
        self.assertContains(response, "chart.js@4.5.1")
        self.assertContains(response, "dashboard-charts.js")
        self.assertContains(response, 'hx-get="/partials/attendance-chart/"')

    def test_attendance_chart_partial_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard_attendance_chart_partial"))
        self.assertEqual(response.status_code, 302)

    def test_attendance_chart_partial_returns_partial_markup(self):
        response = self.client.get(
            reverse("dashboard_attendance_chart_partial"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/partials/attendance_chart.html")
        self.assertContains(response, 'id="attendance-chart"')
        self.assertContains(response, 'id="attendance-chart-data"')
        self.assertNotContains(response, "sidebar")
        self.assertNotContains(response, "chart.js")
