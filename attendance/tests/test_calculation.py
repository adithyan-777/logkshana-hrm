from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from attendance.calculation import attendance_day_for_punch
from attendance.models import AttendanceTransaction
from attendance.services import attendance_transaction_create
from common.tests.base import BaseTenantTestCase
from common.tests.factories import employee_factory, timetable_factory
from schedule.calculation import expected_datetimes
from schedule.models import ScheduleAssignment
from schedule.selectors import timetable_for_employee_on_date
from schedule.services import schedule_assignment_create, shift_create

QATAR = ZoneInfo("Asia/Qatar")


# Pinned so the naive-timestamp test does not depend on the local .env timezone.
@override_settings(TIME_ZONE="Asia/Qatar")
class AttendanceDayForPunchTests(SimpleTestCase):
    DAY_CHANGE_TIME = time(8, 0)

    def test_punch_after_day_change_belongs_to_same_day(self):
        punch = datetime(2026, 3, 10, 9, 0, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2026, 3, 10))

    def test_punch_before_day_change_belongs_to_previous_day(self):
        punch = datetime(2026, 3, 10, 7, 59, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2026, 3, 9))

    def test_punch_exactly_at_day_change_belongs_to_current_day(self):
        punch = datetime(2026, 3, 10, 8, 0, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2026, 3, 10))

    def test_midnight_punch_belongs_to_previous_day(self):
        punch = datetime(2026, 3, 10, 0, 0, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2026, 3, 9))

    def test_overnight_checkout_punch_lands_on_shift_day(self):
        # Night shift Monday 2026-03-09 22:00 -> Tuesday 06:00. The
        # 06:15 check-out punch on Tuesday must be attributed to Monday.
        punch = datetime(2026, 3, 10, 6, 15, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2026, 3, 9))

    def test_utc_timestamp_is_converted_to_local_time(self):
        # 03:15 UTC is 06:15 in Asia/Qatar (+03) -> before day change.
        punch = datetime(2026, 3, 10, 3, 15, tzinfo=UTC)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2026, 3, 9))

    def test_naive_timestamp_is_interpreted_in_local_timezone(self):
        punch = datetime(2026, 3, 10, 6, 15)  # noqa: DTZ001 -- naive input is the point

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2026, 3, 9))

    def test_late_morning_punch_is_not_pulled_back_to_previous_day(self):
        # The day-change rule only pulls early-morning punches back; a
        # 09:00 punch already belongs to its own calendar day.
        punch = datetime(2026, 3, 10, 9, 0, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2026, 3, 10))

    def test_first_of_month_punch_belongs_to_previous_month(self):
        punch = datetime(2026, 3, 1, 6, 0, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2026, 2, 28))

    def test_new_year_punch_belongs_to_previous_year(self):
        punch = datetime(2026, 1, 1, 6, 0, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2025, 12, 31))

    def test_leap_year_punch_belongs_to_leap_day(self):
        punch = datetime(2028, 3, 1, 6, 0, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2028, 2, 29))

    def test_non_leap_year_punch_skips_feb_29(self):
        punch = datetime(2027, 3, 1, 6, 0, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2027, 2, 28))

    def test_late_night_punch_stays_on_same_day(self):
        # An evening-shift check-in at 23:30 is not pulled back.
        punch = datetime(2026, 3, 10, 23, 30, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=self.DAY_CHANGE_TIME
        )

        self.assertEqual(day, date(2026, 3, 10))

    def test_midnight_day_change_time_keeps_everything_on_current_day(self):
        for punch_at in (0, 1):
            with self.subTest(hour=punch_at):
                punch = datetime(2026, 3, 10, 0, punch_at, tzinfo=QATAR)

                day = attendance_day_for_punch(
                    timestamp=punch, day_change_time=time(0, 0)
                )

                self.assertEqual(day, date(2026, 3, 10))

    def test_extreme_day_change_time_pulls_back_evening_punch(self):
        punch = datetime(2026, 3, 10, 23, 0, tzinfo=QATAR)

        day = attendance_day_for_punch(
            timestamp=punch, day_change_time=time(23, 59)
        )

        self.assertEqual(day, date(2026, 3, 9))


class OvernightShiftScenarioTests(BaseTenantTestCase):
    """
    End-to-end overnight shift: Monday 22:00 -> Tuesday 06:00.

    Ties together timetable resolution, expected datetimes, and punch
    attribution, with punches stored and re-fetched through the
    database to exercise the timestamptz round trip.
    """

    def setUp(self):
        super().setUp()
        # class-level override_settings(TIME_ZONE) is unreliable under
        # FastTenantTestCase, so activate the zone explicitly instead.
        timezone.activate(QATAR)
        self.addCleanup(timezone.deactivate)
        self.employee = employee_factory(first_name="Night", emp_code="E900")
        self.night = timetable_factory(
            name="Night",
            code="NIGHT-E2E",
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )
        self.monday = date(2026, 3, 9)
        self.tuesday = date(2026, 3, 10)
        schedule_assignment_create(
            assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
            shift=shift_create(
                name="Monday Nights",
                code="SH-E2E",
                cycle_unit="week",
                shift_days=[{"day_number": 1, "timetable": self.night}],
            ),
            start_date=date(2026, 3, 1),
            end_date=date(2026, 12, 31),
            employee=self.employee,
        )

    def punch(self, *, at, direction=AttendanceTransaction.Direction.IN):
        return attendance_transaction_create(
            employee=self.employee,
            external_id=f"E2E-{self.id()}-{at.isoformat()}",
            timestamp=at,
            direction=direction,
            source=AttendanceTransaction.Source.MANUAL,
        )

    def test_monday_resolves_to_night_shift_tuesday_is_day_off(self):
        self.assertEqual(
            timetable_for_employee_on_date(employee=self.employee, day=self.monday),
            self.night,
        )
        self.assertIsNone(
            timetable_for_employee_on_date(employee=self.employee, day=self.tuesday)
        )

    def test_expected_window_spans_two_calendar_days(self):
        expected_in, expected_out = expected_datetimes(
            timetable=self.night, day=self.monday
        )

        self.assertEqual(
            timezone.localtime(expected_in),
            datetime(2026, 3, 9, 22, 0, tzinfo=QATAR),
        )
        self.assertEqual(
            timezone.localtime(expected_out),
            datetime(2026, 3, 10, 6, 0, tzinfo=QATAR),
        )

    def test_both_overnight_punches_belong_to_shift_day(self):
        self.punch(at=datetime(2026, 3, 9, 21, 55, tzinfo=QATAR))
        self.punch(
            at=datetime(2026, 3, 10, 6, 10, tzinfo=QATAR),
            direction=AttendanceTransaction.Direction.OUT,
        )

        punches = AttendanceTransaction.objects.filter(employee=self.employee)
        self.assertEqual(punches.count(), 2)

        for punch in punches:
            with self.subTest(punch=punch.external_id):
                day = attendance_day_for_punch(
                    timestamp=punch.timestamp,
                    day_change_time=self.night.day_change_time,
                )
                self.assertEqual(day, self.monday)

    def test_tuesday_afternoon_punch_belongs_to_tuesday(self):
        # The day-change rule must only pull back early-morning punches:
        # a Tuesday 14:00 punch belongs to Tuesday, even though a night
        # shift ended earlier that morning.
        punch = self.punch(at=datetime(2026, 3, 10, 14, 0, tzinfo=QATAR))

        day = attendance_day_for_punch(
            timestamp=punch.timestamp,
            day_change_time=self.night.day_change_time,
        )

        self.assertEqual(day, self.tuesday)
