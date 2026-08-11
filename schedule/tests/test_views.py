from uuid import uuid4

from django.urls import reverse
from django_tenants.test.client import TenantClient

from common.tests.base import BaseTenantTestCase
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
