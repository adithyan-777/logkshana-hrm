"""Regression tests for browser-like timetable add POSTs.

Browsers submit optional number inputs as "" and always include the blank
extra break-formset row. Both must validate: blank optionals fall back to
model defaults and untouched break rows are skipped.
"""

from django.urls import reverse

from common.tests.base import BaseTenantTestCase
from schedule.models import Timetable


def _base_data(**overrides):
    data = {
        "name": "Morning",
        "code": "M1",
        "type": "normal",
        "is_active": "True",
        "check_in": "09:00",
        "check_out": "18:00",
        "check_out_cross_days": "",
        "work_minutes": "",
        "check_in_start": "",
        "check_in_end": "",
        "grace_period_minutes": "",
        "breaks-TOTAL_FORMS": "1",
        "breaks-INITIAL_FORMS": "0",
        "breaks-MIN_NUM_FORMS": "0",
        "breaks-MAX_NUM_FORMS": "1000",
        "breaks-0-name": "",
        "breaks-0-break_time_type": "fixed",
        "breaks-0-break_time_minutes": "",
        "breaks-0-start_time": "",
        "breaks-0-end_time": "",
    }
    data.update(overrides)
    return data


class TimetableAddBrowserPostTests(BaseTenantTestCase):
    def test_blank_optionals_and_untouched_break_row_create_timetable(self):
        response = self.client.post(reverse("timetable_add"), _base_data())

        self.assertEqual(response.status_code, 200)
        self.assertIn("timetableCreated", response.headers.get("HX-Trigger"))
        timetable = Timetable.objects.get(name="Morning")
        self.assertEqual(timetable.grace_period_minutes, 0)
        self.assertEqual(timetable.check_out_cross_days, 0)
        self.assertEqual(timetable.breaks.count(), 0)

class TimetableAddDrawerTests(BaseTenantTestCase):
    def test_full_page_get_redirects_to_list_drawer(self):
        response = self.client.get(reverse("timetable_add"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("timetable_list"), response.url)
        self.assertIn("drawer=", response.url)

    def test_htmx_get_returns_form_fragment(self):
        response = self.client.get(reverse("timetable_add"), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="timetable-form"')


class TimetableAddPartialBreakTests(BaseTenantTestCase):
    def test_partial_break_row_fails_validation(self):
        response = self.client.post(
            reverse("timetable_add"),
            _base_data(name="Evening", code="E1", **{"breaks-0-name": "Lunch"}),
        )

        self.assertIsNone(response.headers.get("HX-Trigger"))
        self.assertEqual(Timetable.objects.filter(name="Evening").count(), 0)
        self.assertContains(response, "This field is required.")
