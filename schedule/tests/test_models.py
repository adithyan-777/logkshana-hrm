from datetime import date, time

from django.core.exceptions import ValidationError

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    employee_factory,
    schedule_factory,
    timetable_factory,
)
from schedule.models import EmployeeScheduleOverride, TimetableBreak
from schedule.services import (
    assignment_create,
    schedule_create,
    timetable_break_create,
    timetable_create,
)


class TimetableDayChangeTests(BaseTenantTestCase):
    def test_default_day_change_accepted(self):
        timetable = timetable_create(
            name="Default DC", code="DC-1", check_in=time(9, 0), check_out=time(18, 0)
        )
        self.assertEqual(timetable.day_change_time, time(0, 0))

    def test_default_day_change_for_overnight_shift(self):
        timetable = timetable_create(
            name="Night Watch",
            code="DC-5",
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )
        self.assertEqual(timetable.day_change_time, time(8, 0))

    def test_early_shift_with_early_day_change_accepted(self):
        timetable = timetable_create(
            name="Early Bird",
            code="DC-2",
            check_in=time(6, 0),
            check_out=time(14, 0),
            day_change_time=time(5, 0),
        )
        self.assertEqual(timetable.day_change_time, time(5, 0))

    def test_day_change_after_check_in_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            timetable_create(
                name="Backwards DC",
                code="DC-3",
                check_in=time(9, 0),
                check_out=time(18, 0),
                day_change_time=time(10, 0),
            )
        self.assertIn("day_change_time", ctx.exception.error_dict)

    def test_ordering_violation_rejected_by_model_clean(self):
        with self.assertRaises(ValidationError) as ctx:
            timetable_create(
                name="Inverted",
                code="DC-4",
                check_in=time(18, 0),
                check_out=time(9, 0),
            )
        self.assertIn("check_out_cross_days", ctx.exception.error_dict)


class ScheduleRepeatValidationTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.timetable = timetable_factory(name="Rep", code="REP-1")

    def test_repeat_every_below_one_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            schedule_create(
                name="Zero Interval",
                timetable=self.timetable,
                repeat=True,
                repeat_every=0,
            )
        self.assertIn("repeat_every", ctx.exception.error_dict)

    def test_zero_interval_fine_without_repeat(self):
        schedule = schedule_create(
            name="Non Repeat",
            timetable=self.timetable,
            repeat=False,
            repeat_every=0,
        )
        self.assertFalse(schedule.repeat)


class BreakCleanTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.timetable = timetable_factory(name="Brk", code="BRK-1")

    def test_inverted_break_rejected(self):
        break_ = TimetableBreak(
            timetable=self.timetable,
            name="Bad",
            start_time=time(13, 0),
            end_time=time(12, 0),
        )
        with self.assertRaises(ValidationError) as ctx:
            break_.full_clean()
        self.assertIn("end_time", ctx.exception.error_dict)

    def test_flexible_break_without_minutes_rejected(self):
        break_ = TimetableBreak(
            timetable=self.timetable,
            name="Flex",
            break_time_type=TimetableBreak.BreakType.FLEXIBLE,
            start_time=time(13, 0),
            end_time=time(14, 0),
        )
        with self.assertRaises(ValidationError) as ctx:
            break_.full_clean()
        self.assertIn("break_time_minutes", ctx.exception.error_dict)

    def test_service_break_still_validates_window(self):
        with self.assertRaises(ValidationError):
            timetable_break_create(
                timetable=self.timetable,
                name="Outside",
                start_time=time(19, 0),
                end_time=time(20, 0),
            )


class AssignmentValidationTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.employee = employee_factory(first_name="Ana", emp_code="VA001")
        self.schedule = schedule_factory(
            name="Weekly", timetable=timetable_factory(name="Base", code="VAL-B")
        )

    def test_end_before_start_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            assignment_create(
                schedule=self.schedule,
                employees=[self.employee],
                start_date=date(2026, 3, 1),
                end_date=date(2026, 2, 1),
            )
        self.assertIn("end_date", ctx.exception.error_dict)

    def test_open_ended_assignment_accepted(self):
        assignment = assignment_create(
            schedule=self.schedule,
            employees=[self.employee],
            start_date=date(2026, 3, 1),
            end_date=None,
        )
        self.assertIsNone(assignment.end_date)
        self.assertEqual(
            list(assignment.employees.all()), [self.employee]
        )

    def test_end_on_or_after_start_accepted(self):
        assignment = assignment_create(
            schedule=self.schedule,
            employees=[self.employee],
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 1),
        )
        self.assertEqual(assignment.end_date, date(2026, 3, 1))


class OverrideValidationTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.employee = employee_factory(first_name="Bo", emp_code="VO001")
        self.schedule = schedule_factory(
            name="Swap", timetable=timetable_factory(name="Base", code="VAL-O")
        )

    def _override(self, **kwargs):
        override = EmployeeScheduleOverride(
            employee=self.employee, date=date(2026, 3, 9), **kwargs
        )
        override.full_clean()
        return override

    def test_day_off_without_schedule_accepted(self):
        override = self._override(is_day_off=True)
        self.assertIsNone(override.schedule)

    def test_swap_with_schedule_accepted(self):
        override = self._override(schedule=self.schedule)
        self.assertFalse(override.is_day_off)

    def test_day_off_with_schedule_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self._override(is_day_off=True, schedule=self.schedule)
        self.assertIn("schedule", ctx.exception.error_dict)

    def test_swap_without_schedule_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self._override(is_day_off=False, schedule=None)
        self.assertIn("schedule", ctx.exception.error_dict)
