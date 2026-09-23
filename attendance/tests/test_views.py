from datetime import date

from django.urls import reverse
from django.utils import timezone
from django_tenants.test.client import TenantClient

from attendance.models import Attendance, AttendanceActivity
from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import (
    activity_factory,
    attendance_record_factory,
    employee_factory,
)


class AttendanceActivityViewTests(BaseTenantTestCase):
    def test_list_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("attendance_transaction_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("attendance_transaction_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attendance Punches")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            reverse("attendance_transaction_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transaction_table")

    def test_list_shows_created_activity(self):
        employee = employee_factory(first_name="Visible", emp_code="AT-VIS")
        activity_factory(
            employee=employee,
            external_id="SEARCH-VIS",
        )

        response = self.client.get(
            reverse("attendance_transaction_list"),
            {"q": "visible"},
        )

        self.assertContains(response, "Visible")
        self.assertContains(response, "SEARCH-VIS")

    def test_list_pagination(self):
        for index in range(26):
            activity_factory(
                external_id=f"PAG-{index:02d}",
            )

        page_one = self.client.get(reverse("attendance_transaction_list"))
        page_two = self.client.get(reverse("attendance_transaction_list"), {"page": 2})
        htmx_page_one = self.client.get(
            reverse("attendance_transaction_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(page_one, "Showing 1–25 of 26")
        self.assertContains(page_two, "Showing 26–26 of 26")
        self.assertContains(htmx_page_one, 'class="pagination"')
        self.assertEqual(page_one.content.count(b"<tr>"), 26)
        self.assertEqual(page_two.content.count(b"<tr>"), 2)

    def test_add_creates_activity(self):
        employee = employee_factory(first_name="View", emp_code="AT300")
        punch_time = timezone.now().strftime("%Y-%m-%dT%H:%M")

        response = self.client.post(
            reverse("attendance_transaction_add"),
            {
                "employee": employee.pk,
                "punch_time": punch_time,
                "direction": "in",
                "method": "manual",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("HX-Trigger"), "attendanceTransactionCreated"
        )
        punch = AttendanceActivity.objects.filter(employee=employee).first()
        self.assertIsNotNone(punch)
        self.assertTrue(punch.external_id.startswith("manual:"))


class AttendanceRecordViewTests(BaseTenantTestCase):
    def test_list_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("daily_attendance_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("daily_attendance_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Daily Attendance")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            reverse("daily_attendance_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "daily_table")

    def test_list_shows_created_record(self):
        employee = employee_factory(first_name="DailyVis", emp_code="DA-VIS")
        attendance_record_factory(
            employee=employee,
            day=date(2026, 7, 15),
            status=Attendance.Status.PRESENT,
        )

        response = self.client.get(
            reverse("daily_attendance_list"),
            {"q": "dailyvis"},
        )

        self.assertContains(response, "DailyVis")
        self.assertContains(response, "Present")

    def test_add_creates_daily_record(self):
        employee = employee_factory(first_name="DailyView", emp_code="DA300")

        response = self.client.post(
            reverse("daily_attendance_add"),
            {
                "employee": employee.pk,
                "day": "2026-07-01",
                "status": "present",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "dailyAttendanceCreated")
        self.assertTrue(
            Attendance.objects.filter(
                employee=employee,
                day=date(2026, 7, 1),
            ).exists()
        )


class MyAttendanceViewTests(BaseTenantTestCase):
    def _employee_client(self, *, first_name="Self", emp_code="ME-001"):
        employee = employee_factory(first_name=first_name, emp_code=emp_code)
        user = employee.user
        user.set_password(TEST_PASSWORD)
        user.save()
        client = TenantClient(self.tenant)
        self.assertTrue(client.login(email=user.email, password=TEST_PASSWORD))
        return employee, client

    def test_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("my_attendance"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_shows_only_own_daily_records(self):
        employee, client = self._employee_client()
        other = employee_factory(first_name="OtherPerson", emp_code="ME-OTH")
        attendance_record_factory(
            employee=employee,
            day=date(2026, 8, 10),
            status=Attendance.Status.PRESENT,
        )
        attendance_record_factory(
            employee=other,
            day=date(2026, 8, 11),
            status=Attendance.Status.ABSENT,
        )

        response = client.get(reverse("my_attendance"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Attendance")
        self.assertContains(response, "Present")
        self.assertNotContains(response, "Absent")
        self.assertNotContains(response, "OtherPerson")
        self.assertContains(response, "/attendance/me/")

    def test_shows_own_punches_without_daily_row(self):
        employee, client = self._employee_client(emp_code="ME-P1")
        punch = activity_factory(employee=employee)
        # Simulate punches with no calculated daily row (e.g. row removed
        # or not yet processed): the user must still see their punches.
        Attendance.objects.filter(employee=employee).delete()
        other = employee_factory(first_name="OtherPerson", emp_code="ME-POTH")
        activity_factory(employee=other)

        response = client.get(reverse("my_attendance"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recent punches")
        self.assertEqual(list(response.context["recent_punches"]), [punch])

    def test_forbidden_on_company_attendance_list(self):
        _employee, client = self._employee_client(emp_code="ME-403")

        response = client.get(reverse("attendance_transaction_list"))

        self.assertEqual(response.status_code, 403)
