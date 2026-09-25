"""Breaks: multiple rows per timetable, contained in work time, no overlaps."""

from datetime import time

from django.core.exceptions import ValidationError
from django.urls import reverse

from common.tests.base import BaseTenantTestCase
from schedule.models import Timetable
from schedule.services import (
    timetable_break_create,
    timetable_create,
    validate_break_within_timetable,
)
from schedule.tests.test_timetable_add import _base_data


def _break_data(index, *, name, start, end):
    return {
        f"breaks-{index}-name": name,
        f"breaks-{index}-break_time_type": "fixed",
        f"breaks-{index}-break_time_minutes": "",
        f"breaks-{index}-start_time": start,
        f"breaks-{index}-end_time": end,
    }


def _two_breaks_data(**overrides):
    data = _base_data(**overrides)
    data["breaks-TOTAL_FORMS"] = "2"
    return data


class BreakContainmentTests(BaseTenantTestCase):
    def test_inside_hours_ok(self):
        validate_break_within_timetable(
            start_time=time(13, 0),
            end_time=time(14, 0),
            check_in=time(9, 0),
            check_out=time(18, 0),
        )

    def test_boundary_times_ok(self):
        validate_break_within_timetable(
            start_time=time(9, 0),
            end_time=time(18, 0),
            check_in=time(9, 0),
            check_out=time(18, 0),
        )

    def test_outside_hours_rejected(self):
        with self.assertRaises(ValidationError):
            validate_break_within_timetable(
                start_time=time(19, 0),
                end_time=time(20, 0),
                check_in=time(9, 0),
                check_out=time(18, 0),
            )

    def test_partial_overlap_rejected(self):
        with self.assertRaises(ValidationError):
            validate_break_within_timetable(
                start_time=time(17, 30),
                end_time=time(18, 30),
                check_in=time(9, 0),
                check_out=time(18, 0),
            )

    def test_overnight_break_after_midnight_ok(self):
        validate_break_within_timetable(
            start_time=time(1, 0),
            end_time=time(1, 30),
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )

    def test_overnight_break_outside_rejected(self):
        with self.assertRaises(ValidationError):
            validate_break_within_timetable(
                start_time=time(8, 0),
                end_time=time(9, 0),
                check_in=time(22, 0),
                check_out=time(6, 0),
                check_out_cross_days=1,
            )

    def test_service_create_outside_hours_rejected(self):
        timetable = timetable_create(
            name="Day", check_in=time(9, 0), check_out=time(18, 0)
        )
        with self.assertRaises(ValidationError):
            timetable_break_create(
                timetable=timetable,
                name="Late",
                start_time=time(19, 0),
                end_time=time(20, 0),
            )
        self.assertEqual(timetable.breaks.count(), 0)


class TimetableBreakFormsetTests(BaseTenantTestCase):
    def test_two_breaks_create_timetable(self):
        data = _two_breaks_data(name="Split", code="S1")
        data.update(_break_data(0, name="Lunch", start="13:00", end="14:00"))
        data.update(_break_data(1, name="Tea", start="16:00", end="16:15"))

        response = self.client.post(reverse("timetable_add"), data)

        self.assertIsNotNone(response.headers.get("HX-Trigger"))
        timetable = Timetable.objects.get(name="Split")
        self.assertEqual(timetable.breaks.count(), 2)

    def test_break_outside_hours_rejected(self):
        data = _two_breaks_data(name="Bad", code="B1")
        data.update(_break_data(0, name="Lunch", start="13:00", end="14:00"))
        data.update(_break_data(1, name="Night", start="19:00", end="20:00"))

        response = self.client.post(reverse("timetable_add"), data)

        self.assertIsNone(response.headers.get("HX-Trigger"))
        self.assertEqual(Timetable.objects.filter(name="Bad").count(), 0)
        self.assertContains(response, "within working hours")

    def test_overlapping_breaks_rejected(self):
        data = _two_breaks_data(name="Overlap", code="O1")
        data.update(_break_data(0, name="First", start="13:00", end="14:00"))
        data.update(_break_data(1, name="Second", start="13:30", end="14:30"))

        response = self.client.post(reverse("timetable_add"), data)

        self.assertIsNone(response.headers.get("HX-Trigger"))
        self.assertEqual(Timetable.objects.filter(name="Overlap").count(), 0)
        self.assertContains(response, "must not overlap")
