from datetime import date, datetime, timedelta

from django.urls import reverse
from django.utils import timezone
from django_tenants.test.client import TenantClient

from attendance.models import Attendance
from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import (
    activity_factory,
    attendance_record_factory,
    department_factory,
    employee_factory,
    leave_request_factory,
    leave_type_factory,
)
from leave.models import LeaveBalance, LeaveRequest
from reports.exports import ReportData, render_report_response
from reports.selectors.attendance import (
    attendance_summary_list,
    department_attendance_list,
    individual_attendance_list,
)
from reports.selectors.exceptions import exception_report_list
from reports.selectors.leave import (
    leave_balance_list,
    leave_utilization_list,
    pending_leave_list,
)
from reports.selectors.overtime import overtime_report_list
from reports.selectors.punch_log import punch_log_list


class AttendanceSummarySelectorTests(BaseTenantTestCase):
    def test_aggregates_by_employee(self):
        department = department_factory(name="Sales", code="SAL")
        employee = employee_factory(
            first_name="Alice",
            emp_code="R001",
            department=department,
        )
        present = attendance_record_factory(
            employee=employee,
            day=date(2026, 2, 1),
            status=Attendance.Status.PRESENT,
        )
        present.total_work_time = timedelta(minutes=480)
        present.late_time = timedelta(minutes=10)
        present.save(update_fields=["total_work_time", "late_time"])
        attendance_record_factory(
            employee=employee,
            day=date(2026, 2, 2),
            status=Attendance.Status.ABSENT,
        )

        results = list(
            attendance_summary_list(
                date_from=date(2026, 2, 1),
                date_to=date(2026, 2, 28),
            )
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["present_days"], 1)
        self.assertEqual(results[0]["absent_days"], 1)
        self.assertEqual(results[0]["total_late"], timedelta(minutes=10))


class IndividualAttendanceSelectorTests(BaseTenantTestCase):
    def test_filters_by_employee(self):
        employee = employee_factory(first_name="Bob", emp_code="R002")
        other = employee_factory(first_name="Other", emp_code="R003")
        attendance_record_factory(employee=employee, day=date(2026, 3, 1))
        attendance_record_factory(employee=other, day=date(2026, 3, 1))

        results = list(
            individual_attendance_list(
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 31),
                employee_id=employee.pk,
            )
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].employee, employee)


class DepartmentAttendanceSelectorTests(BaseTenantTestCase):
    def test_groups_by_department(self):
        department = department_factory(name="Ops", code="OPS")
        employee = employee_factory(
            first_name="Carol", emp_code="R004", department=department
        )
        attendance_record_factory(
            employee=employee,
            day=date(2026, 4, 1),
            status=Attendance.Status.PRESENT,
        )

        results = list(
            department_attendance_list(
                date_from=date(2026, 4, 1),
                date_to=date(2026, 4, 30),
            )
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["employee__department__name"], "Ops")
        self.assertEqual(results[0]["present_days"], 1)


class ExceptionReportSelectorTests(BaseTenantTestCase):
    def test_includes_missing_punch_records(self):
        employee = employee_factory(first_name="Dave", emp_code="R005")
        attendance_record_factory(
            employee=employee,
            day=date(2026, 5, 1),
            status=Attendance.Status.INCOMPLETE,
        )

        results = list(
            exception_report_list(
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 31),
                exception_type="missing_punch",
            )
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, Attendance.Status.INCOMPLETE)


class PunchLogSelectorTests(BaseTenantTestCase):
    def test_filters_by_date_range(self):
        employee = employee_factory(first_name="Eve", emp_code="R006")
        activity_factory(
            employee=employee,
            punch_time=timezone.make_aware(datetime(2026, 6, 1, 9, 0)),
        )

        results = list(
            punch_log_list(
                date_from=date(2026, 6, 1),
                date_to=date(2026, 6, 30),
            )
        )

        self.assertEqual(len(results), 1)


class OvertimeReportSelectorTests(BaseTenantTestCase):
    def test_filters_by_status(self):
        employee = employee_factory(first_name="Frank", emp_code="R007")
        record = attendance_record_factory(
            employee=employee,
            day=date(2026, 7, 1),
            status=Attendance.Status.PRESENT,
        )
        record.over_time = timedelta(minutes=60)
        record.save(update_fields=["over_time"])

        results = list(
            overtime_report_list(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 31),
                status=Attendance.Status.PRESENT,
            )
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].overtime_minutes, 60)


class LeaveReportSelectorTests(BaseTenantTestCase):
    def test_leave_balance_filters_by_year(self):
        employee = employee_factory(first_name="Grace", emp_code="R008")
        leave_type = leave_type_factory(name="Annual", code="ANN-R")
        LeaveBalance.objects.create(
            employee=employee,
            leave_type=leave_type,
            year=2026,
            entitled_days=30,
            used_days=5,
        )

        results = list(leave_balance_list(year=2026))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].available_days, 25)

    def test_leave_utilization_returns_approved_requests(self):
        employee = employee_factory(first_name="Henry", emp_code="R009")
        leave_request_factory(
            employee=employee,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 3),
            status=LeaveRequest.Status.APPROVED,
        )

        results = list(
            leave_utilization_list(
                date_from=date(2026, 8, 1),
                date_to=date(2026, 8, 31),
            )
        )

        self.assertEqual(len(results), 1)

    def test_pending_leave_returns_pending_requests(self):
        employee = employee_factory(first_name="Ivy", emp_code="R010")
        leave_request_factory(
            employee=employee,
            status=LeaveRequest.Status.PENDING,
        )

        results = list(pending_leave_list())

        self.assertEqual(len(results), 1)


class ExportTests(BaseTenantTestCase):
    def test_csv_xlsx_and_pdf_responses(self):
        data = ReportData(
            title="Test Report",
            headers=["Name", "Value"],
            rows=[["Alice", 1]],
        )

        csv_response = render_report_response(
            data=data,
            filename="test-report",
            export_format="csv",
        )
        xlsx_response = render_report_response(
            data=data,
            filename="test-report",
            export_format="xlsx",
        )
        pdf_response = render_report_response(
            data=data,
            filename="test-report",
            export_format="pdf",
        )

        self.assertEqual(csv_response["Content-Type"], "text/csv")
        self.assertIn(
            "spreadsheetml.sheet",
            xlsx_response["Content-Type"],
        )
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertIn(b"Alice", csv_response.content)


class ReportViewTests(BaseTenantTestCase):
    def test_hub_returns_200(self):
        response = self.client.get(reverse("report_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reports")

    def test_attendance_summary_html_and_exports(self):
        employee = employee_factory(first_name="View", emp_code="R011")
        attendance_record_factory(employee=employee, day=date(2026, 9, 1))

        for export_format in ("csv", "xlsx", "pdf"):
            response = self.client.get(
                reverse("report_attendance_summary"),
                {
                    "date_from": "2026-09-01",
                    "date_to": "2026-09-30",
                    "format": export_format,
                },
            )
            self.assertEqual(response.status_code, 200)

        response = self.client.get(
            reverse("report_attendance_summary"),
            {"date_from": "2026-09-01", "date_to": "2026-09-30"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attendance Summary")

    def test_all_report_urls_return_200(self):
        urls = [
            "report_attendance_summary",
            "report_department_attendance",
            "report_exceptions",
            "report_punch_log",
            "report_overtime",
            "report_leave",
        ]
        for url_name in urls:
            response = self.client.get(
                reverse(url_name),
                {"date_from": "2026-01-01", "date_to": "2026-12-31"},
            )
            self.assertEqual(response.status_code, 200, msg=url_name)

    def test_individual_report_requires_employee_for_data(self):
        employee = employee_factory(first_name="Ind", emp_code="R012")
        attendance_record_factory(employee=employee, day=date(2026, 10, 1))

        response = self.client.get(
            reverse("report_individual_attendance"),
            {
                "date_from": "2026-10-01",
                "date_to": "2026-10-31",
                "employee": employee.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ind")


class ReportSelfServiceTests(BaseTenantTestCase):
    """Employees with only ATTENDANCE_OWN_VIEW can see their own records
    in the punch-log and individual reports, nothing else."""

    def _employee_client(self, *, first_name="Self", emp_code="RS-001"):
        employee = employee_factory(first_name=first_name, emp_code=emp_code)
        user = employee.user
        user.set_password(TEST_PASSWORD)
        user.save()
        client = TenantClient(self.tenant)
        self.assertTrue(client.login(email=user.email, password=TEST_PASSWORD))
        return employee, client

    def test_punch_log_shows_only_own_punches(self):
        employee, client = self._employee_client()
        own_punch = activity_factory(
            employee=employee,
            punch_time=timezone.make_aware(datetime(2026, 9, 2, 9, 0)),
        )
        other = employee_factory(first_name="OtherPerson", emp_code="RS-OTH")
        other_punch = activity_factory(
            employee=other,
            punch_time=timezone.make_aware(datetime(2026, 9, 2, 9, 0)),
        )

        response = client.get(
            reverse("report_punch_log"),
            {"date_from": "2026-09-01", "date_to": "2026-09-30"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "only your own punches")
        self.assertContains(response, own_punch.external_id)
        self.assertNotContains(response, other_punch.external_id)

    def test_punch_log_ignores_employee_spoof_param(self):
        employee, client = self._employee_client(emp_code="RS-002")
        own_punch = activity_factory(
            employee=employee,
            punch_time=timezone.make_aware(datetime(2026, 9, 2, 9, 0)),
        )
        other = employee_factory(first_name="OtherPerson", emp_code="RS-OTH2")
        other_punch = activity_factory(
            employee=other,
            punch_time=timezone.make_aware(datetime(2026, 9, 2, 9, 0)),
        )

        response = client.get(
            reverse("report_punch_log"),
            {
                "date_from": "2026-09-01",
                "date_to": "2026-09-30",
                "employee": other.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_punch.external_id)
        self.assertNotContains(response, other_punch.external_id)

    def test_individual_auto_selects_own_employee(self):
        employee, client = self._employee_client(emp_code="RS-003")
        attendance_record_factory(
            employee=employee,
            day=date(2026, 9, 5),
            status=Attendance.Status.PRESENT,
        )
        other = employee_factory(first_name="OtherPerson", emp_code="RS-OTH3")
        attendance_record_factory(
            employee=other,
            day=date(2026, 9, 6),
            status=Attendance.Status.ABSENT,
        )

        response = client.get(
            reverse("report_individual_attendance"),
            {"date_from": "2026-09-01", "date_to": "2026-09-30"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["employee_selected"])
        self.assertEqual(len(response.context["report_rows"]), 1)
        self.assertContains(response, "only your own timesheet")

    def test_other_reports_still_forbidden(self):
        _employee, client = self._employee_client(emp_code="RS-004")

        for url_name in (
            "report_hub",
            "report_attendance_summary",
            "report_department_attendance",
            "report_exceptions",
            "report_overtime",
            "report_leave",
        ):
            response = client.get(reverse(url_name))
            self.assertEqual(response.status_code, 403, msg=url_name)


class ReportPaginationTests(BaseTenantTestCase):
    def test_attendance_summary_pagination_and_full_export(self):
        for index in range(26):
            employee = employee_factory(
                first_name=f"Report{index:02d}",
                emp_code=f"R-PG-{index:02d}",
            )
            attendance_record_factory(
                employee=employee,
                day=date(2026, 9, 1),
            )

        page_one = self.client.get(
            reverse("report_attendance_summary"),
            {"date_from": "2026-09-01", "date_to": "2026-09-30"},
        )
        page_two = self.client.get(
            reverse("report_attendance_summary"),
            {"date_from": "2026-09-01", "date_to": "2026-09-30", "page": 2},
        )
        export_response = self.client.get(
            reverse("report_attendance_summary"),
            {
                "date_from": "2026-09-01",
                "date_to": "2026-09-30",
                "page": 2,
                "format": "csv",
            },
        )

        self.assertContains(page_one, "Showing 1–25 of 26")
        self.assertContains(page_two, "Showing 26–26 of 26")
        self.assertEqual(page_one.content.count(b"<tr>"), 26)
        self.assertEqual(page_two.content.count(b"<tr>"), 2)
        self.assertEqual(len(export_response.content.decode().splitlines()), 27)
