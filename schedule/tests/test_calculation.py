from datetime import date, time

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from schedule.calculation import expected_datetimes
from schedule.models import Timetable


def build_timetable(**kwargs) -> Timetable:
    fields = {
        "name": "Shift",
        "code": "SHIFT",
        "type": Timetable.Type.NORMAL,
        "work_type": Timetable.WorkType.WORK,
    }
    fields.update(kwargs)
    return Timetable(**fields)


# Pinned so boundary behaviour does not depend on the local .env timezone.
@override_settings(TIME_ZONE="Asia/Qatar")
class ExpectedDatetimesTests(SimpleTestCase):
    def test_same_day_shift_stays_on_one_date(self):
        timetable = build_timetable(check_in=time(9, 0), check_out=time(18, 0))

        expected_in, expected_out = expected_datetimes(
            timetable=timetable, day=date(2026, 3, 9)
        )

        self.assertEqual(timezone.localtime(expected_in).date(), date(2026, 3, 9))
        self.assertEqual(timezone.localtime(expected_in).time(), time(9, 0))
        self.assertEqual(timezone.localtime(expected_out).date(), date(2026, 3, 9))
        self.assertEqual(timezone.localtime(expected_out).time(), time(18, 0))

    def test_overnight_shift_pushes_checkout_to_next_day(self):
        timetable = build_timetable(
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_in_cross_days=0,
            check_out_cross_days=1,
        )

        expected_in, expected_out = expected_datetimes(
            timetable=timetable, day=date(2026, 3, 9)  # Monday
        )

        self.assertEqual(timezone.localtime(expected_in).date(), date(2026, 3, 9))
        self.assertEqual(timezone.localtime(expected_in).time(), time(22, 0))
        self.assertEqual(timezone.localtime(expected_out).date(), date(2026, 3, 10))
        self.assertEqual(timezone.localtime(expected_out).time(), time(6, 0))

    def test_multi_day_checkout_offset(self):
        timetable = build_timetable(
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=2,
        )

        expected_in, expected_out = expected_datetimes(
            timetable=timetable, day=date(2026, 3, 9)
        )

        self.assertEqual(timezone.localtime(expected_in).date(), date(2026, 3, 9))
        self.assertEqual(timezone.localtime(expected_out).date(), date(2026, 3, 11))

    def test_check_in_cross_day_offset(self):
        timetable = build_timetable(
            check_in=time(0, 30),
            check_out=time(8, 0),
            check_in_cross_days=1,
            check_out_cross_days=1,
        )

        expected_in, expected_out = expected_datetimes(
            timetable=timetable, day=date(2026, 3, 9)
        )

        self.assertEqual(timezone.localtime(expected_in).date(), date(2026, 3, 10))
        self.assertEqual(timezone.localtime(expected_in).time(), time(0, 30))
        self.assertEqual(timezone.localtime(expected_out).date(), date(2026, 3, 10))

    def test_expected_datetimes_are_timezone_aware(self):
        timetable = build_timetable(check_in=time(9, 0), check_out=time(18, 0))

        expected_in, expected_out = expected_datetimes(
            timetable=timetable, day=date(2026, 3, 9)
        )

        self.assertTrue(timezone.is_aware(expected_in))
        self.assertTrue(timezone.is_aware(expected_out))

    def test_day_off_timetable_has_no_expected_times(self):
        timetable = build_timetable(work_type=Timetable.WorkType.OFF)

        expected_in, expected_out = expected_datetimes(
            timetable=timetable, day=date(2026, 3, 9)
        )

        self.assertIsNone(expected_in)
        self.assertIsNone(expected_out)

    def test_flexible_timetable_without_times_has_no_expected_times(self):
        timetable = build_timetable(
            type=Timetable.Type.FLEXIBLE,
            work_minutes=480,
        )

        expected_in, expected_out = expected_datetimes(
            timetable=timetable, day=date(2026, 3, 9)
        )

        self.assertIsNone(expected_in)
        self.assertIsNone(expected_out)

    def test_overnight_shift_crossing_month_boundary(self):
        timetable = build_timetable(
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )

        _, expected_out = expected_datetimes(
            timetable=timetable, day=date(2026, 1, 31)
        )

        self.assertEqual(timezone.localtime(expected_out).date(), date(2026, 2, 1))

    def test_overnight_shift_crossing_year_boundary(self):
        timetable = build_timetable(
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )

        _, expected_out = expected_datetimes(
            timetable=timetable, day=date(2025, 12, 31)
        )

        self.assertEqual(timezone.localtime(expected_out).date(), date(2026, 1, 1))

    def test_overnight_shift_into_leap_day(self):
        timetable = build_timetable(
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )

        _, expected_out = expected_datetimes(
            timetable=timetable, day=date(2028, 2, 28)
        )

        self.assertEqual(timezone.localtime(expected_out).date(), date(2028, 2, 29))

    def test_overnight_shift_skips_feb_29_in_non_leap_year(self):
        timetable = build_timetable(
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )

        _, expected_out = expected_datetimes(
            timetable=timetable, day=date(2027, 2, 28)
        )

        self.assertEqual(timezone.localtime(expected_out).date(), date(2027, 3, 1))
