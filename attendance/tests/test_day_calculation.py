from datetime import datetime, time
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from attendance.calculation import (
    attendance_day_for_punch,
    day_variances,
    dedupe_punches,
    direction_from_gateway_status,
    effective_directions,
    pair_punches,
    scheduled_minutes,
    summarize_pairs,
)


def aware(*args):
    return timezone.make_aware(datetime(*args))  # noqa: DTZ001 -- naive input is the point


def punch_at(*args, direction="unknown"):
    return SimpleNamespace(punch_time=aware(*args), direction=direction)


def office_timetable(**overrides):
    base = {
        "check_in": time(9, 0),
        "check_out": time(18, 0),
        "work_minutes": None,
        "count_break_time_as_work_time": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def fixed_break(start, end, **overrides):
    base = {"start_time": start, "end_time": end, "break_time_type": "fixed"}
    base.update(overrides)
    return SimpleNamespace(**base)


class PairingTests(SimpleTestCase):
    def test_basic_in_out_pair(self):
        punches = [
            punch_at(2026, 3, 9, 9, 0, direction="in"),
            punch_at(2026, 3, 9, 18, 0, direction="out"),
        ]
        summary = summarize_pairs(pair_punches(dedupe_punches(punches)))

        self.assertEqual(summary.worked_minutes, 540)
        self.assertTrue(summary.has_check_in)
        self.assertTrue(summary.has_check_out)

    def test_unknown_directions_alternate(self):
        punches = [
            punch_at(2026, 3, 9, 9, 0),
            punch_at(2026, 3, 9, 13, 0),
            punch_at(2026, 3, 9, 14, 0),
            punch_at(2026, 3, 9, 18, 0),
        ]
        summary = summarize_pairs(pair_punches(dedupe_punches(punches)))

        self.assertEqual(summary.worked_minutes, 480)  # 4h + 4h
        self.assertEqual(summary.break_minutes, 60)

    def test_double_tap_is_deduped(self):
        punches = [
            punch_at(2026, 3, 9, 9, 0, 0, direction="in"),
            punch_at(2026, 3, 9, 9, 0, 20, direction="in"),
            punch_at(2026, 3, 9, 18, 0, direction="out"),
        ]
        kept = dedupe_punches(punches, window_minutes=1)

        self.assertEqual(len(kept), 2)

    def test_trailing_lone_check_in_is_open(self):
        punches = [punch_at(2026, 3, 9, 9, 0, direction="in")]
        summary = summarize_pairs(pair_punches(punches))

        self.assertTrue(summary.has_check_in)
        self.assertFalse(summary.has_check_out)
        self.assertEqual(summary.worked_minutes, 0)

    def test_repeat_check_in_ignored_without_multiple_flag(self):
        punches = [
            punch_at(2026, 3, 9, 9, 0, direction="in"),
            punch_at(2026, 3, 9, 9, 30, direction="in"),
            punch_at(2026, 3, 9, 18, 0, direction="out"),
        ]
        summary = summarize_pairs(pair_punches(punches))

        self.assertEqual(summary.worked_minutes, 540)


class BreakAwarePairingTests(SimpleTestCase):
    windows = [(time(13, 0), time(14, 0))]

    def test_break_punch_counts_as_going_out(self):
        punches = [
            punch_at(2026, 3, 9, 9, 0, direction="in"),
            punch_at(2026, 3, 9, 13, 5),
            punch_at(2026, 3, 9, 14, 0),
            punch_at(2026, 3, 9, 18, 0, direction="out"),
        ]

        self.assertEqual(
            effective_directions(punches, break_windows=self.windows),
            ["in", "out", "in", "out"],
        )
        summary = summarize_pairs(
            pair_punches(punches, break_windows=self.windows)
        )

        self.assertEqual(summary.worked_minutes, 245 + 240)
        self.assertEqual(summary.break_minutes, 55)

    def test_punch_after_break_counts_as_back_in(self):
        punches = [
            punch_at(2026, 3, 9, 9, 0, direction="in"),
            punch_at(2026, 3, 9, 13, 5),
            punch_at(2026, 3, 9, 18, 0),
        ]

        self.assertEqual(
            effective_directions(punches, break_windows=self.windows),
            ["in", "out", "in"],
        )
        summary = summarize_pairs(
            pair_punches(punches, break_windows=self.windows)
        )

        # Morning period closed at the break punch; the 18:00 punch
        # re-opens as back-in and stays open (no checkout after it).
        self.assertEqual(summary.worked_minutes, 245)
        self.assertEqual(summary.pairs[-1][0].punch_time.hour, 18)
        self.assertIsNone(summary.pairs[-1][1])

    def test_no_windows_keeps_plain_alternation(self):
        punches = [
            punch_at(2026, 3, 9, 9, 0),
            punch_at(2026, 3, 9, 13, 5),
            punch_at(2026, 3, 9, 14, 0),
            punch_at(2026, 3, 9, 18, 0),
        ]

        self.assertEqual(
            effective_directions(punches), ["in", "out", "in", "out"]
        )


class GatewayStatusTests(SimpleTestCase):
    def test_explicit_out_states(self):
        for code in (1, 2, 5):
            self.assertEqual(direction_from_gateway_status(code), "out")

    def test_garbled_status_is_unknown(self):
        self.assertEqual(direction_from_gateway_status(None), "unknown")
        self.assertEqual(direction_from_gateway_status("bogus"), "unknown")
        self.assertEqual(direction_from_gateway_status(0), "unknown")


class DayAttributionTests(SimpleTestCase):
    def test_early_morning_punch_belongs_to_previous_day(self):
        day = attendance_day_for_punch(
            timestamp=aware(2026, 3, 10, 6, 15), day_change_time=time(8, 0)
        )

        self.assertEqual(day, aware(2026, 3, 9).date())


class ScheduledMinutesTests(SimpleTestCase):
    def test_span_minus_unpaid_break(self):
        timetable = office_timetable()
        expected_in = aware(2026, 3, 9, 9, 0)
        expected_out = aware(2026, 3, 9, 18, 0)
        breaks = [fixed_break(time(13, 0), time(14, 0))]

        self.assertEqual(
            scheduled_minutes(
                timetable=timetable,
                expected_in=expected_in,
                expected_out=expected_out,
                breaks=breaks,
            ),
            480,
        )

    def test_paid_break_time_counts_as_work(self):
        timetable = office_timetable(count_break_time_as_work_time=True)
        expected_in = aware(2026, 3, 9, 9, 0)
        expected_out = aware(2026, 3, 9, 18, 0)
        breaks = [fixed_break(time(13, 0), time(14, 0))]

        self.assertEqual(
            scheduled_minutes(
                timetable=timetable,
                expected_in=expected_in,
                expected_out=expected_out,
                breaks=breaks,
            ),
            540,
        )

    def test_flexible_timetable_falls_back_to_work_minutes(self):
        timetable = office_timetable(work_minutes=480)

        self.assertEqual(
            scheduled_minutes(
                timetable=timetable, expected_in=None, expected_out=None
            ),
            480,
        )

    def test_overnight_post_midnight_break_counts_once(self):
        timetable = office_timetable()
        expected_in = aware(2026, 3, 9, 22, 0)
        expected_out = aware(2026, 3, 10, 6, 0)
        breaks = [fixed_break(time(2, 0), time(2, 30))]

        self.assertEqual(
            scheduled_minutes(
                timetable=timetable,
                expected_in=expected_in,
                expected_out=expected_out,
                breaks=breaks,
            ),
            480 - 30,
        )

    def test_overnight_evening_break_counts_once(self):
        timetable = office_timetable()
        expected_in = aware(2026, 3, 9, 22, 0)
        expected_out = aware(2026, 3, 10, 6, 0)
        breaks = [fixed_break(time(23, 0), time(23, 30))]

        self.assertEqual(
            scheduled_minutes(
                timetable=timetable,
                expected_in=expected_in,
                expected_out=expected_out,
                breaks=breaks,
            ),
            480 - 30,
        )

    def test_day_shift_break_not_double_counted(self):
        timetable = office_timetable()
        expected_in = aware(2026, 3, 9, 9, 0)
        expected_out = aware(2026, 3, 9, 18, 0)
        breaks = [
            fixed_break(time(13, 0), time(14, 0)),
            fixed_break(time(16, 0), time(16, 15)),
        ]

        self.assertEqual(
            scheduled_minutes(
                timetable=timetable,
                expected_in=expected_in,
                expected_out=expected_out,
                breaks=breaks,
            ),
            540 - 75,
        )


class DayVariancesTests(SimpleTestCase):
    def test_late_after_grace(self):
        variances = day_variances(
            first_in=aware(2026, 3, 9, 9, 10),
            last_out=aware(2026, 3, 9, 18, 0),
            worked_minutes=530,
            expected_in=aware(2026, 3, 9, 9, 0),
            expected_out=aware(2026, 3, 9, 18, 0),
            scheduled=480,
            late_grace_minutes=5,
        )

        self.assertEqual(variances.late_minutes, 5)
        self.assertEqual(variances.early_minutes, 0)
        self.assertEqual(variances.overtime_minutes, 50)

    def test_early_checkout(self):
        variances = day_variances(
            first_in=aware(2026, 3, 9, 9, 0),
            last_out=aware(2026, 3, 9, 17, 30),
            worked_minutes=450,
            expected_in=aware(2026, 3, 9, 9, 0),
            expected_out=aware(2026, 3, 9, 18, 0),
            scheduled=480,
        )

        self.assertEqual(variances.early_minutes, 30)
        self.assertEqual(variances.overtime_minutes, 0)

    def test_no_expected_times_gives_zero_variances(self):
        variances = day_variances(
            first_in=aware(2026, 3, 9, 9, 0),
            last_out=aware(2026, 3, 9, 18, 0),
            worked_minutes=540,
            expected_in=None,
            expected_out=None,
            scheduled=480,
        )

        self.assertEqual(variances.late_minutes, 0)
        self.assertEqual(variances.early_minutes, 0)
        self.assertEqual(variances.overtime_minutes, 60)
