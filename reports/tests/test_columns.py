from datetime import date

from django.test import RequestFactory
from django.urls import reverse

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    daily_attendance_factory,
    department_factory,
    employee_factory,
)
from attendance.models import DailyAttendance
from reports.columns import (
    ATTENDANCE_SUMMARY,
    INDIVIDUAL_ATTENDANCE,
    REPORT_COLUMNS,
    all_columns,
    filter_columns,
    resolve_report_columns,
)
from reports.models import ReportColumnPreference
from reports.report_data import attendance_summary_report_data
from reports.services import get_preferred_columns, save_preferred_columns

FEB_RANGE = {"date_from": "2026-02-01", "date_to": "2026-02-28"}


def _attendance_for(employee=None):
    return daily_attendance_factory(
        employee=employee,
        date=date(2026, 2, 1),
        status=DailyAttendance.Status.PRESENT,
    )


class ColumnRegistryTests(BaseTenantTestCase):
    def _request(self, query=""):
        request = RequestFactory().get(f"/?{query}")
        request.user = self.user
        return request

    def test_filter_columns_drops_invalid_and_keeps_registry_order(self):
        columns = filter_columns(
            ATTENDANCE_SUMMARY,
            ["present_days", "bogus", "employee", ""],
        )
        self.assertEqual(
            [column.key for column in columns],
            ["employee", "present_days"],
        )

    def test_resolve_prefers_url_param_over_preference(self):
        save_preferred_columns(self.user, ATTENDANCE_SUMMARY, ["absent_days"])
        request = self._request("fields=employee,present_days")

        columns = resolve_report_columns(
            request, report_key=ATTENDANCE_SUMMARY, preferred_keys=["absent_days"]
        )
        self.assertEqual(
            [column.key for column in columns], ["employee", "present_days"]
        )

    def test_resolve_falls_back_to_preference_then_all(self):
        request = self._request()
        columns = resolve_report_columns(
            request, report_key=ATTENDANCE_SUMMARY, preferred_keys=["employee"]
        )
        self.assertEqual([column.key for column in columns], ["employee"])

        columns = resolve_report_columns(
            request, report_key=ATTENDANCE_SUMMARY, preferred_keys=None
        )
        self.assertEqual(columns, all_columns(ATTENDANCE_SUMMARY))

    def test_resolve_invalid_url_param_falls_back_to_preference(self):
        request = self._request("fields=not_a_column")
        columns = resolve_report_columns(
            request, report_key=ATTENDANCE_SUMMARY, preferred_keys=["employee"]
        )
        self.assertEqual([column.key for column in columns], ["employee"])


class PreferenceServiceTests(BaseTenantTestCase):
    def test_save_and_get_round_trip(self):
        saved = save_preferred_columns(
            self.user, ATTENDANCE_SUMMARY, ["employee", "present_days", "bogus"]
        )
        self.assertEqual(saved, ["employee", "present_days"])

        self.assertEqual(
            get_preferred_columns(self.user, ATTENDANCE_SUMMARY),
            ["employee", "present_days"],
        )

    def test_get_returns_none_when_unsaved(self):
        self.assertIsNone(get_preferred_columns(self.user, ATTENDANCE_SUMMARY))

    def test_save_updates_existing_preference(self):
        save_preferred_columns(self.user, ATTENDANCE_SUMMARY, ["employee"])
        save_preferred_columns(self.user, ATTENDANCE_SUMMARY, ["present_days"])

        self.assertEqual(
            ReportColumnPreference.objects.filter(
                user=self.user, report_key=ATTENDANCE_SUMMARY
            ).count(),
            1,
        )
        self.assertEqual(
            get_preferred_columns(self.user, ATTENDANCE_SUMMARY), ["present_days"]
        )


class ReportProjectionTests(BaseTenantTestCase):
    def test_summary_report_data_projects_selected_columns(self):
        row = {
            "employee__emp_code": "E1",
            "employee__first_name": "Ada",
            "employee__last_name": "Lovelace",
            "employee__department__name": "",
            "total_days": 1,
            "present_days": 1,
            "absent_days": 0,
            "late_days": 0,
            "leave_days": 0,
            "total_worked_minutes": 90,
            "total_late_minutes": 0,
            "total_overtime_minutes": 0,
        }

        columns = filter_columns(ATTENDANCE_SUMMARY, ["present_days", "employee"])
        data = attendance_summary_report_data([row], columns)

        self.assertEqual(data.headers, ["Employee", "Present"])
        self.assertEqual(data.rows, [["Ada Lovelace", 1]])


class ReportColumnViewTests(BaseTenantTestCase):
    def test_summary_view_renders_only_selected_columns(self):
        _attendance_for(employee_factory())
        url = reverse("report_attendance_summary")

        response = self.client.get(
            url, {**FEB_RANGE, "fields": "employee,present_days"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<th>Employee</th>")
        self.assertContains(response, "<th>Present</th>")
        self.assertNotContains(response, "<th>Absent</th>")

    def test_summary_export_respects_selected_columns(self):
        _attendance_for(employee_factory())
        url = reverse("report_attendance_summary")

        response = self.client.get(
            url, {**FEB_RANGE, "fields": "employee", "format": "csv"}
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Employee", content)
        self.assertNotIn("Absent", content)

    def test_columns_panel_lists_available_columns(self):
        employee_factory()
        url = reverse("report_attendance_summary")

        response = self.client.get(url)
        self.assertContains(response, "Save as my default")
        for column in REPORT_COLUMNS[ATTENDANCE_SUMMARY]:
            self.assertContains(response, column.label)

    def test_preference_applies_when_no_url_param(self):
        _attendance_for(employee_factory())
        save_preferred_columns(self.user, ATTENDANCE_SUMMARY, ["employee"])

        response = self.client.get(reverse("report_attendance_summary"), FEB_RANGE)
        self.assertContains(response, "<th>Employee</th>")
        self.assertNotContains(response, "<th>Absent</th>")

    def test_save_columns_view_persists_selection(self):
        url = reverse("report_save_columns")

        response = self.client.post(
            url,
            {"report_key": ATTENDANCE_SUMMARY, "fields": ["employee", "present_days"]},
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            get_preferred_columns(self.user, ATTENDANCE_SUMMARY),
            ["employee", "present_days"],
        )

    def test_save_columns_view_rejects_unknown_report(self):
        response = self.client.post(
            reverse("report_save_columns"),
            {"report_key": "nope", "fields": ["employee"]},
        )
        self.assertEqual(response.status_code, 400)

    def test_save_columns_view_rejects_empty_selection(self):
        response = self.client.post(
            reverse("report_save_columns"),
            {"report_key": ATTENDANCE_SUMMARY, "fields": ["bogus"]},
        )
        self.assertEqual(response.status_code, 400)

    def test_individual_view_uses_columns(self):
        employee = employee_factory()
        _attendance_for(employee)
        url = reverse("report_individual_attendance")

        response = self.client.get(
            url, {**FEB_RANGE, "employee": employee.pk, "fields": "date,status"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<th>Date</th>")
        self.assertNotContains(response, "<th>First In</th>")

    def test_department_view_uses_columns(self):
        department = department_factory()
        _attendance_for(employee_factory(department=department))
        url = reverse("report_department_attendance")

        response = self.client.get(url, {**FEB_RANGE, "fields": "department"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<th>Department</th>")
        self.assertNotContains(response, "<th>Absent</th>")

    def test_individual_registry_has_worked_column(self):
        self.assertIn("worked", {c.key for c in REPORT_COLUMNS[INDIVIDUAL_ATTENDANCE]})
