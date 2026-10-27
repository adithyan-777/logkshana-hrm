from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.utils import timezone

from common.tests.base import BaseTenantTestCase
from common.tests.factories import employee_factory, schedule_factory, timetable_factory
from schedule.calculation import expected_datetimes
from schedule.models import EmployeeScheduleAssignment
from schedule.selectors import timetable_for_employee_on_date

QATAR = ZoneInfo("Asia/Qatar")


class OvernightShiftScenarioTests(BaseTenantTestCase):
    """
    End-to-end overnight shift: Monday 22:00 -> Tuesday 06:00.

    Ties together timetable resolution and expected datetimes through
    the database (timestamptz round trip). Punch attribution lives in
    the (future) daily calculation and is not exercised here.
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
        schedule = schedule_factory(
            name="Monday Nights",
            timetable=self.night,
        )
        assignment = EmployeeScheduleAssignment.objects.create(
            schedule=schedule,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 12, 31),
        )
        assignment.employees.add(self.employee)

    def test_both_days_resolve_to_night_shift(self):
        # The simplified schedule model has no per-weekday timetables:
        # an assigned weekly schedule covers every day in range.
        self.assertEqual(
            timetable_for_employee_on_date(employee=self.employee, day=self.monday),
            self.night,
        )
        self.assertEqual(
            timetable_for_employee_on_date(employee=self.employee, day=self.tuesday),
            self.night,
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
