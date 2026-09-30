from datetime import date

from django.urls import reverse

from common.tests.base import BaseTenantTestCase
from common.tests.factories import schedule_factory, timetable_factory
from schedule.models import Schedule
from schedule.services import schedule_create


class ScheduleWindowServiceTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.timetable = timetable_factory(name="Win", code="WIN-01")

    def test_create_with_window_persists_both_dates(self):
        schedule = schedule_create(
            name="Q1 Window",
            timetable=self.timetable,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )
        self.assertEqual(schedule.start_date, date(2026, 1, 1))
        self.assertEqual(schedule.end_date, date(2026, 3, 31))

    def test_end_before_start_rejected(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as ctx:
            schedule_create(
                name="Backwards",
                timetable=self.timetable,
                start_date=date(2026, 3, 1),
                end_date=date(2026, 2, 1),
            )
        self.assertIn("end_date", ctx.exception.error_dict)

    def test_blank_window_stays_open_ended(self):
        schedule = schedule_create(name="Open", timetable=self.timetable)
        self.assertIsNone(schedule.start_date)
        self.assertIsNone(schedule.end_date)


class ScheduleAddViewWindowTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.timetable = timetable_factory(name="Form Win", code="FW-01")

    def _data(self, **overrides):
        data = {
            "name": "Windowed",
            "timetable": str(self.timetable.pk),
            "start_date": "2026-01-01",
            "end_date": "2026-06-30",
            "repeat": "on",
            "repeat_every": "1",
            "repeat_unit": "week",
        }
        data.update(overrides)
        return data

    def test_post_saves_window(self):
        response = self.client.post(reverse("schedule_add"), self._data())

        self.assertEqual(response.status_code, 200)
        schedule = Schedule.objects.get(name="Windowed")
        self.assertEqual(schedule.start_date, date(2026, 1, 1))
        self.assertEqual(schedule.end_date, date(2026, 6, 30))

    def test_end_before_start_rejected_on_form(self):
        response = self.client.post(
            reverse("schedule_add"),
            self._data(end_date="2025-12-31"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("HX-Trigger"))
        self.assertFalse(Schedule.objects.filter(name="Windowed").exists())
        self.assertContains(response, "End date must not be before start date.")

    def test_blank_end_date_renders_open_ended(self):
        response = self.client.post(
            reverse("schedule_add"),
            self._data(end_date=""),
        )

        schedule = Schedule.objects.get(name="Windowed")
        self.assertIsNone(schedule.end_date)
        self.assertContains(response, "End date (blank = open-ended)")

    def test_edit_round_trips_window(self):
        schedule = schedule_factory(
            name="Round Trip",
            timetable=self.timetable,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )

        response = self.client.post(
            reverse("schedule_edit", args=[schedule.pk]),
            self._data(
                name="Round Trip",
                start_date="2026-02-01",
                end_date="2026-11-30",
            ),
        )

        self.assertEqual(response.status_code, 200)
        schedule.refresh_from_db()
        self.assertEqual(schedule.start_date, date(2026, 2, 1))
        self.assertEqual(schedule.end_date, date(2026, 11, 30))
