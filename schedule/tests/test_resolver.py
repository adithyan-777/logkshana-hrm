from datetime import date, time

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    employee_factory,
    schedule_factory,
    timetable_factory,
)
from schedule.models import (
    EmployeeScheduleAssignment,
    EmployeeScheduleOverride,
    Schedule,
)
from schedule.selectors import (
    resolve_schedule_for_employee_on_date,
    schedule_is_active_on,
    timetable_for_employee_on_date,
)


def _assign(*, schedule, employee, start, end=None, priority=0):
    assignment = EmployeeScheduleAssignment.objects.create(
        schedule=schedule,
        start_date=start,
        end_date=end,
        priority=priority,
    )
    assignment.employees.add(employee)
    return assignment


class ResolveScheduleTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.employee = employee_factory(first_name="Roster", emp_code="RS001")
        self.morning = timetable_factory(
            name="Morning",
            code="MORN-RS",
            check_in=time(9, 0),
            check_out=time(18, 0),
        )
        self.night = timetable_factory(
            name="Night",
            code="NIGHT-RS",
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )
        self.monday = date(2026, 3, 9)

    def test_assignment_hit_returns_timetable(self):
        schedule = schedule_factory(name="Weekly Mornings", timetable=self.morning)
        _assign(
            schedule=schedule,
            employee=self.employee,
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
        )

        resolved = resolve_schedule_for_employee_on_date(
            employee=self.employee, day=self.monday
        )

        self.assertFalse(resolved.is_day_off)
        self.assertEqual(resolved.schedule, schedule)
        self.assertEqual(resolved.timetable, self.morning)
        self.assertEqual(
            timetable_for_employee_on_date(
                employee=self.employee, day=self.monday
            ),
            self.morning,
        )

    def test_day_off_override_wins_over_assignment(self):
        schedule = schedule_factory(name="Weekly Mornings", timetable=self.morning)
        _assign(
            schedule=schedule,
            employee=self.employee,
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
        )
        EmployeeScheduleOverride.objects.create(
            employee=self.employee, date=self.monday, is_day_off=True
        )

        resolved = resolve_schedule_for_employee_on_date(
            employee=self.employee, day=self.monday
        )

        self.assertTrue(resolved.is_day_off)
        self.assertIsNone(resolved.timetable)
        self.assertIsNone(
            timetable_for_employee_on_date(
                employee=self.employee, day=self.monday
            )
        )

    def test_swap_override_wins_over_assignment(self):
        schedule_factory(name="Weekly Mornings", timetable=self.morning)
        morning_schedule = schedule_factory(
            name="Assigned Mornings", timetable=self.morning
        )
        _assign(
            schedule=morning_schedule,
            employee=self.employee,
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
        )
        night_schedule = schedule_factory(
            name="One-off Nights", timetable=self.night
        )
        EmployeeScheduleOverride.objects.create(
            employee=self.employee, date=self.monday, schedule=night_schedule
        )

        resolved = resolve_schedule_for_employee_on_date(
            employee=self.employee, day=self.monday
        )

        self.assertFalse(resolved.is_day_off)
        self.assertEqual(resolved.timetable, self.night)

    def test_higher_priority_assignment_wins(self):
        low = schedule_factory(name="Low Priority", timetable=self.morning)
        _assign(
            schedule=low,
            employee=self.employee,
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
            priority=0,
        )
        high = schedule_factory(name="High Priority", timetable=self.night)
        _assign(
            schedule=high,
            employee=self.employee,
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
            priority=10,
        )

        resolved = resolve_schedule_for_employee_on_date(
            employee=self.employee, day=self.monday
        )

        self.assertEqual(resolved.timetable, self.night)

    def test_inactive_timetable_resolves_to_none(self):
        self.morning.is_active = False
        self.morning.save(update_fields=["is_active"])
        schedule = schedule_factory(name="Weekly Mornings", timetable=self.morning)
        _assign(
            schedule=schedule,
            employee=self.employee,
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
        )

        resolved = resolve_schedule_for_employee_on_date(
            employee=self.employee, day=self.monday
        )

        self.assertFalse(resolved.is_day_off)
        self.assertIsNone(resolved.timetable)

    def test_biweekly_repeat_skips_alternate_week(self):
        schedule = schedule_factory(
            name="Biweekly",
            timetable=self.morning,
            repeat_every=2,
            repeat_unit=Schedule.RepeatUnitType.WEEK,
        )
        schedule.start_date = date(2026, 3, 9)
        schedule.save(update_fields=["start_date"])
        _assign(
            schedule=schedule,
            employee=self.employee,
            start=date(2026, 3, 1),
            end=date(2026, 12, 31),
        )

        on_week = resolve_schedule_for_employee_on_date(
            employee=self.employee, day=date(2026, 3, 9)
        )
        off_week = resolve_schedule_for_employee_on_date(
            employee=self.employee, day=date(2026, 3, 16)
        )

        self.assertEqual(on_week.timetable, self.morning)
        self.assertIsNone(off_week.timetable)

    def test_no_assignment_resolves_to_none(self):
        resolved = resolve_schedule_for_employee_on_date(
            employee=self.employee, day=self.monday
        )

        self.assertFalse(resolved.is_day_off)
        self.assertIsNone(resolved.schedule)
        self.assertIsNone(resolved.timetable)


class ScheduleIsActiveOnTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.timetable = timetable_factory(name="Base", code="BASE-ACT")
        self.schedule = schedule_factory(
            name="Base Schedule", timetable=self.timetable
        )

    def test_non_repeating_schedule_covers_window(self):
        self.schedule.repeat = False
        self.schedule.start_date = date(2026, 3, 1)
        self.schedule.end_date = date(2026, 3, 31)
        self.schedule.save()

        self.assertTrue(
            schedule_is_active_on(schedule=self.schedule, day=date(2026, 3, 15))
        )
        self.assertFalse(
            schedule_is_active_on(schedule=self.schedule, day=date(2026, 4, 1))
        )

    def test_null_anchor_is_always_active(self):
        self.schedule.start_date = None
        self.schedule.end_date = None
        self.schedule.save(update_fields=["start_date", "end_date"])

        self.assertTrue(
            schedule_is_active_on(schedule=self.schedule, day=date(2026, 3, 15))
        )

    def test_inactive_schedule_is_never_active(self):
        self.schedule.is_active = False
        self.schedule.save(update_fields=["is_active"])

        self.assertFalse(
            schedule_is_active_on(schedule=self.schedule, day=date(2026, 3, 15))
        )
