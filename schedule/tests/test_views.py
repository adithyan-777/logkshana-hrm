from uuid import uuid4

from django.urls import reverse
from django_tenants.test.client import TenantClient

from common.tests.base import BaseTenantTestCase
from common.tests.factories import timetable_factory
from schedule.models import Timetable


class TimetableViewTests(BaseTenantTestCase):
    def test_list_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("timetable_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("timetable_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Timetables")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            reverse("timetable_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "schedule/partials/timetable_table.html")

    def test_list_pagination(self):
        for index in range(26):
            timetable_factory(
                name=f"Timetable {index:02d}",
                code=f"TT-PG-{index:02d}",
            )

        page_one = self.client.get(reverse("timetable_list"))
        page_two = self.client.get(reverse("timetable_list"), {"page": 2})
        htmx_page_one = self.client.get(
            reverse("timetable_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(page_one, "Showing 1–25 of 26")
        self.assertContains(page_two, "Showing 26–26 of 26")
        self.assertContains(htmx_page_one, 'class="pagination"')
        self.assertEqual(page_one.content.count(b"<tr>"), 26)
        self.assertEqual(page_two.content.count(b"<tr>"), 2)

    def test_add_creates_timetable(self):
        code = f"MORN-{uuid4().hex[:6]}"
        response = self.client.post(
            reverse("timetable_add"),
            {
                "name": "Morning",
                "code": code,
                "type": "normal",
                "work_type": "work",
                "workday": "1",
                "late_in_grace_minutes": "0",
                "early_out_grace_minutes": "0",
                "check_in_cross_days": "0",
                "check_out_cross_days": "0",
                "day_change_time": "08:00",
                "require_check_in": "on",
                "require_check_out": "on",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "timetableCreated")
        self.assertTrue(Timetable.objects.filter(code=code).exists())


class ShiftViewTests(BaseTenantTestCase):
    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("shift_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shifts")
