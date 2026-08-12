from datetime import date
from uuid import uuid4

from django.urls import reverse
from django.utils import timezone
from django_tenants.test.client import TenantClient

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    attendance_correction_factory,
    attendance_rule_factory,
    attendance_transaction_factory,
    daily_attendance_factory,
    employee_factory,
)
from attendance.forms import AttendanceCorrectionForm, AttendanceRuleForm
from attendance.models import (
    AttendanceCorrection,
    AttendanceRule,
    AttendanceTransaction,
    DailyAttendance,
)


class AttendanceCorrectionFormTests(BaseTenantTestCase):
    def test_rejects_check_out_before_check_in(self):
        employee = employee_factory(first_name="Form", emp_code="AF100")
        check_in = timezone.now()
        check_out = check_in.replace(hour=check_in.hour - 1)

        form = AttendanceCorrectionForm(
            data={
                "employee": employee.pk,
                "date": "2026-06-01",
                "check_in": check_in.strftime("%Y-%m-%dT%H:%M"),
                "check_out": check_out.strftime("%Y-%m-%dT%H:%M"),
                "reason": "Test",
                "status": "pending",
            }
        )
        form.fields["check_in"].input_formats = ["%Y-%m-%dT%H:%M"]
        form.fields["check_out"].input_formats = ["%Y-%m-%dT%H:%M"]

        self.assertFalse(form.is_valid())
        self.assertIn("check_out", form.errors)


class AttendanceTransactionViewTests(BaseTenantTestCase):
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
        self.assertTemplateUsed(response, "attendance/partials/transaction_table.html")

    def test_list_shows_created_transaction(self):
        employee = employee_factory(first_name="Visible", emp_code="AT-VIS")
        attendance_transaction_factory(
            employee=employee,
            external_id="SEARCH-VIS",
        )

        response = self.client.get(
            reverse("attendance_transaction_list"),
            {"q": "visible"},
        )

        self.assertContains(response, "Visible")
        self.assertContains(response, "SEARCH-VIS")

    def test_add_creates_transaction(self):
        employee = employee_factory(first_name="View", emp_code="AT300")
        external_id = f"EXT-{uuid4().hex[:6]}"
        timestamp = timezone.now().strftime("%Y-%m-%dT%H:%M")

        response = self.client.post(
            reverse("attendance_transaction_add"),
            {
                "employee": employee.pk,
                "external_id": external_id,
                "timestamp": timestamp,
                "direction": "in",
                "source": "manual",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "attendanceTransactionCreated")
        self.assertTrue(
            AttendanceTransaction.objects.filter(external_id=external_id).exists()
        )


class DailyAttendanceViewTests(BaseTenantTestCase):
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
        self.assertTemplateUsed(response, "attendance/partials/daily_table.html")

    def test_list_shows_created_record(self):
        employee = employee_factory(first_name="DailyVis", emp_code="DA-VIS")
        daily_attendance_factory(
            employee=employee,
            date=date(2026, 7, 15),
            status=DailyAttendance.Status.PRESENT,
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
                "date": "2026-07-01",
                "status": "present",
                "scheduled_minutes": "480",
                "worked_minutes": "450",
                "late_minutes": "0",
                "early_leave_minutes": "0",
                "overtime_minutes": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "dailyAttendanceCreated")
        self.assertTrue(
            DailyAttendance.objects.filter(
                employee=employee,
                date=date(2026, 7, 1),
            ).exists()
        )


class AttendanceCorrectionViewTests(BaseTenantTestCase):
    def test_list_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("attendance_correction_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("attendance_correction_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attendance Corrections")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            reverse("attendance_correction_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "attendance/partials/correction_table.html")

    def test_list_shows_created_correction(self):
        employee = employee_factory(first_name="CorrectVis", emp_code="AC-VIS")
        attendance_correction_factory(
            employee=employee,
            reason="Device offline at gate",
        )

        response = self.client.get(
            reverse("attendance_correction_list"),
            {"q": "offline"},
        )

        self.assertContains(response, "CorrectVis")
        self.assertContains(response, "Device offline")

    def test_add_creates_correction(self):
        employee = employee_factory(first_name="Correct", emp_code="AC300")
        check_in = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)

        response = self.client.post(
            reverse("attendance_correction_add"),
            {
                "employee": employee.pk,
                "date": "2026-06-15",
                "check_in": check_in.strftime("%Y-%m-%dT%H:%M"),
                "reason": "Missed morning punch",
                "status": "pending",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "attendanceCorrectionCreated")
        self.assertTrue(
            AttendanceCorrection.objects.filter(
                employee=employee,
                date=date(2026, 6, 15),
                reason="Missed morning punch",
            ).exists()
        )

    def test_add_rejects_invalid_check_out(self):
        employee = employee_factory(first_name="Invalid", emp_code="AC301")
        check_in = timezone.now()
        check_out = check_in.replace(hour=check_in.hour - 2)

        response = self.client.post(
            reverse("attendance_correction_add"),
            {
                "employee": employee.pk,
                "date": "2026-06-16",
                "check_in": check_in.strftime("%Y-%m-%dT%H:%M"),
                "check_out": check_out.strftime("%Y-%m-%dT%H:%M"),
                "reason": "Bad times",
                "status": "pending",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response.headers)
        self.assertFalse(
            AttendanceCorrection.objects.filter(
                employee=employee,
                date=date(2026, 6, 16),
            ).exists()
        )


class AttendanceRuleViewTests(BaseTenantTestCase):
    def test_list_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("attendance_rule_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("attendance_rule_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attendance Rules")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            reverse("attendance_rule_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "attendance/partials/rule_table.html")

    def test_list_shows_created_rule(self):
        attendance_rule_factory(name="Strict Grace Rule")

        response = self.client.get(
            reverse("attendance_rule_list"),
            {"q": "strict grace"},
        )

        self.assertContains(response, "Strict Grace Rule")

    def test_add_creates_rule(self):
        response = self.client.post(
            reverse("attendance_rule_add"),
            {
                "name": "Test Rule",
                "require_check_in": "on",
                "require_check_out": "on",
                "missing_check_in_as_absence": "on",
                "missing_check_out_as_incomplete": "on",
                "late_grace_minutes": "10",
                "early_leave_grace_minutes": "5",
                "late_to_absence_minutes": "60",
                "duplicate_punch_window_minutes": "1",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "attendanceRuleCreated")
        self.assertTrue(AttendanceRule.objects.filter(name="Test Rule").exists())

    def test_rule_form_requires_name(self):
        form = AttendanceRuleForm(data={"name": ""})

        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
