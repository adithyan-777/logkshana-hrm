from datetime import date
from uuid import uuid4

from django.urls import reverse
from django_tenants.test.client import TenantClient

from common.tests.base import BaseTenantTestCase
from common.tests.factories import employee_factory, leave_type_factory
from leave.forms import HolidayForm, LeaveRequestForm, LeaveTypeForm
from leave.models import Holiday, LeaveRequest, LeaveType


class LeaveTypeFormTests(BaseTenantTestCase):
    def test_requires_name_and_code(self):
        form = LeaveTypeForm(data={"name": "", "code": ""})

        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("code", form.errors)


class LeaveRequestFormTests(BaseTenantTestCase):
    def test_rejects_end_date_before_start_date(self):
        employee = employee_factory(first_name="Form", emp_code="LR300")
        leave_type = leave_type_factory(name="Annual", code="ANN-F")

        form = LeaveRequestForm(
            data={
                "employee": employee.pk,
                "leave_type": leave_type.pk,
                "start_date": "2026-06-10",
                "end_date": "2026-06-01",
                "duration_type": "full_day",
                "days": "1",
                "status": "draft",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("end_date", form.errors)


class HolidayFormTests(BaseTenantTestCase):
    def test_rejects_end_date_before_start_date(self):
        form = HolidayForm(
            data={
                "name": "Bad Holiday",
                "date": "2026-07-10",
                "end_date": "2026-07-01",
                "holiday_type": "public",
                "is_active": True,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("end_date", form.errors)


class LeaveTypeViewTests(BaseTenantTestCase):
    def test_list_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("leave_type_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("leave_type_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leave Types")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            reverse("leave_type_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "leave_type_table")

    def test_list_pagination(self):
        for index in range(26):
            leave_type_factory(
                name=f"Leave Type {index:02d}",
                code=f"LT-PG-{index:02d}",
            )

        page_one = self.client.get(reverse("leave_type_list"))
        page_two = self.client.get(reverse("leave_type_list"), {"page": 2})
        htmx_page_one = self.client.get(
            reverse("leave_type_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(page_one, "Showing 1–25 of 26")
        self.assertContains(page_two, "Showing 26–26 of 26")
        self.assertContains(htmx_page_one, 'class="pagination"')
        self.assertEqual(page_one.content.count(b"<tr>"), 26)
        self.assertEqual(page_two.content.count(b"<tr>"), 2)

    def test_add_creates_leave_type(self):
        code = f"LT-{uuid4().hex[:6]}"
        response = self.client.post(
            reverse("leave_type_add"),
            {
                "name": "Casual Leave",
                "code": code,
                "paid": "on",
                "requires_approval": "on",
                "allow_half_day": "on",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "leaveTypeCreated")
        self.assertTrue(LeaveType.objects.filter(code=code).exists())


class LeaveRequestViewTests(BaseTenantTestCase):
    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("leave_request_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leave Requests")

    def test_add_creates_leave_request(self):
        employee = employee_factory(first_name="Request", emp_code="LR400")
        leave_type = leave_type_factory(name="Annual", code="ANN-V")

        response = self.client.post(
            reverse("leave_request_add"),
            {
                "employee": employee.pk,
                "leave_type": leave_type.pk,
                "start_date": "2026-08-01",
                "end_date": "2026-08-05",
                "duration_type": "full_day",
                "days": "5",
                "status": "pending",
                "reason": "Family trip",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "leaveRequestCreated")
        self.assertTrue(
            LeaveRequest.objects.filter(
                employee=employee,
                start_date=date(2026, 8, 1),
            ).exists()
        )


class HolidayViewTests(BaseTenantTestCase):
    def test_add_creates_holiday(self):
        response = self.client.post(
            reverse("holiday_add"),
            {
                "name": "Labour Day",
                "date": "2026-05-01",
                "holiday_type": "public",
                "description": "International Workers Day",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "holidayCreated")
        self.assertTrue(Holiday.objects.filter(name="Labour Day").exists())
