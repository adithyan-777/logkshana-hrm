from datetime import date, time

from django.utils import timezone

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    department_factory,
    employee_factory,
    shift_factory,
    timetable_factory,
)
from schedule.calculation import expected_datetimes
from schedule.models import ScheduleAssignment, Timetable
from schedule.selectors import (
    schedule_assignment_list,
    shift_list,
    temporary_schedule_list,
    timetable_for_employee_on_date,
    timetable_list,
)
from schedule.services import (
    schedule_assignment_create,
    shift_create,
    temporary_schedule_create,
)


class TimetableListTests(BaseTenantTestCase):
    def test_returns_all_timetables_ordered_by_name(self):
        timetable_factory(name="Evening", code="EVE")
        timetable_factory(name="Morning", code="MORN")

        results = list(timetable_list())

        self.assertEqual([t.code for t in results], ["EVE", "MORN"])

    def test_filters_by_search(self):
        timetable_factory(name="Morning Shift", code="MORN")
        timetable_factory(name="Night Shift", code="NIGHT")

        results = list(timetable_list(search="night"))

        self.assertEqual(results[0].code, "NIGHT")

    def test_excludes_soft_deleted_timetables(self):
        timetable = timetable_factory(name="Deleted", code="DEL")
        timetable.delete()

        self.assertEqual(timetable_list().count(), 0)
        self.assertEqual(Timetable.all_objects.count(), 1)


class ShiftListTests(BaseTenantTestCase):
    def test_filters_by_search(self):
        shift_factory(name="Alpha Shift", code="ALPHA")
        shift_factory(name="Beta Shift", code="BETA")

        results = list(shift_list(search="beta"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "BETA")


class ScheduleAssignmentListTests(BaseTenantTestCase):
    def test_filters_by_employee_name(self):
        shift = shift_factory(name="Weekly", code="WEEK-S")
        employee = employee_factory(first_name="Alice", emp_code="E300")
        schedule_assignment_create(
            assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
            shift=shift,
            start_date="2026-01-01",
            end_date="2026-12-31",
            employee=employee,
        )

        results = list(schedule_assignment_list(search="alice"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].employee, employee)

    def test_filters_by_department_name(self):
        shift = shift_factory(name="Weekly", code="WEEK-D")
        department = department_factory(name="Finance", code="FIN")
        schedule_assignment_create(
            assignment_type=ScheduleAssignment.AssignmentType.DEPARTMENT,
            shift=shift,
            start_date="2026-01-01",
            end_date="2026-12-31",
            department=department,
        )

        results = list(schedule_assignment_list(search="finance"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].department, department)


class TemporaryScheduleListTests(BaseTenantTestCase):
    def test_filters_by_reason(self):
        employee = employee_factory(first_name="Bob", emp_code="E400")
        timetable = timetable_factory(name="Special", code="SPEC")
        temporary_schedule_create(
            employee=employee,
            date="2026-03-01",
            timetable=timetable,
            reason="Holiday coverage",
        )

        results = list(temporary_schedule_list(search="holiday"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason, "Holiday coverage")


class TimetableForEmployeeOnDateTests(BaseTenantTestCase):
    """Cross-day and cycle-resolution behaviour of schedule lookup."""

    def setUp(self):
        super().setUp()
        self.morning = timetable_factory(name="Morning", code="MORN-RES")
        self.night = timetable_factory(
            name="Night",
            code="NIGHT-RES",
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )
        self.day_off = timetable_factory(
            name="Off Day", code="OFF-RES", work_type=Timetable.WorkType.OFF
        )
        self.employee = employee_factory(first_name="Res", emp_code="E500")
        self.monday = date(2026, 3, 9)  # 2026-03-09 is a Monday

    def assign_week(
        self,
        *,
        code,
        shift_days,
        employee=None,
        department=None,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 12, 31),
        cycle_unit="week",
        cycle_count=1,
    ):
        return schedule_assignment_create(
            assignment_type=(
                ScheduleAssignment.AssignmentType.EMPLOYEE
                if employee
                else ScheduleAssignment.AssignmentType.DEPARTMENT
            ),
            shift=shift_create(
                name=code,
                code=code,
                cycle_unit=cycle_unit,
                cycle_count=cycle_count,
                shift_days=shift_days,
            ),
            start_date=start_date,
            end_date=end_date,
            employee=employee,
            department=department,
        )

    def test_returns_none_without_assignment(self):
        self.assertIsNone(
            timetable_for_employee_on_date(employee=self.employee, day=self.monday)
        )

    def test_returns_timetable_from_employee_assignment(self):
        self.assign_week(
            code="SH-EMP",
            employee=self.employee,
            shift_days=[{"day_number": 1, "timetable": self.morning}],
        )

        resolved = timetable_for_employee_on_date(
            employee=self.employee, day=self.monday
        )

        self.assertEqual(resolved, self.morning)

    def test_weekly_cycle_maps_iso_weekdays(self):
        self.assign_week(
            code="SH-ISO",
            employee=self.employee,
            shift_days=[
                {"day_number": 1, "timetable": self.morning},
                {"day_number": 3, "timetable": self.night},
            ],
        )

        # Monday -> day 1, Wednesday -> day 3, Saturday -> unmapped day off.
        self.assertEqual(
            timetable_for_employee_on_date(
                employee=self.employee, day=date(2026, 3, 9)
            ),
            self.morning,
        )
        self.assertEqual(
            timetable_for_employee_on_date(
                employee=self.employee, day=date(2026, 3, 11)
            ),
            self.night,
        )
        self.assertIsNone(
            timetable_for_employee_on_date(
                employee=self.employee, day=date(2026, 3, 14)
            )
        )

    def test_department_assignment_applies_to_employee_in_department(self):
        department = department_factory(name="Ops", code="OPS-RES")
        employee = employee_factory(
            first_name="Dep", emp_code="E501", department=department
        )
        self.assign_week(
            code="SH-DEP",
            department=department,
            shift_days=[{"day_number": 1, "timetable": self.morning}],
        )

        resolved = timetable_for_employee_on_date(employee=employee, day=self.monday)

        self.assertEqual(resolved, self.morning)

    def test_employee_assignment_wins_over_department_assignment(self):
        department = department_factory(name="Support", code="SUP-RES")
        employee = employee_factory(
            first_name="Both", emp_code="E502", department=department
        )
        self.assign_week(
            code="SH-DEP2",
            department=department,
            shift_days=[{"day_number": 1, "timetable": self.night}],
        )
        self.assign_week(
            code="SH-EMP2",
            employee=employee,
            shift_days=[{"day_number": 1, "timetable": self.morning}],
        )

        resolved = timetable_for_employee_on_date(employee=employee, day=self.monday)

        self.assertEqual(resolved, self.morning)

    def test_latest_start_date_wins_on_overlap(self):
        self.assign_week(
            code="SH-OLD",
            employee=self.employee,
            start_date=date(2026, 1, 1),
            shift_days=[{"day_number": 1, "timetable": self.morning}],
        )
        self.assign_week(
            code="SH-NEW",
            employee=self.employee,
            start_date=date(2026, 3, 5),
            shift_days=[{"day_number": 1, "timetable": self.night}],
        )

        resolved = timetable_for_employee_on_date(
            employee=self.employee, day=self.monday
        )

        self.assertEqual(resolved, self.night)

    def test_temporary_schedule_overrides_normal_schedule(self):
        self.assign_week(
            code="SH-TMP",
            employee=self.employee,
            shift_days=[{"day_number": 1, "timetable": self.morning}],
        )
        temporary_schedule_create(
            employee=self.employee,
            date=self.monday,
            timetable=self.night,
            reason="Covering the night shift",
        )

        resolved = timetable_for_employee_on_date(
            employee=self.employee, day=self.monday
        )

        self.assertEqual(resolved, self.night)

    def test_non_overriding_temporary_schedule_is_ignored(self):
        self.assign_week(
            code="SH-NOTMP",
            employee=self.employee,
            shift_days=[{"day_number": 1, "timetable": self.morning}],
        )
        temporary_schedule_create(
            employee=self.employee,
            date=self.monday,
            timetable=self.night,
            reason="Extra night shift",
            overrides_normal_schedule=False,
        )

        resolved = timetable_for_employee_on_date(
            employee=self.employee, day=self.monday
        )

        self.assertEqual(resolved, self.morning)

    def test_assignment_boundaries_are_inclusive(self):
        self.assign_week(
            code="SH-BOUND",
            employee=self.employee,
            start_date=self.monday,
            end_date=date(2026, 3, 10),
            shift_days=[
                {"day_number": 1, "timetable": self.morning},
                {"day_number": 2, "timetable": self.morning},
            ],
        )

        self.assertEqual(
            timetable_for_employee_on_date(employee=self.employee, day=self.monday),
            self.morning,
        )
        self.assertEqual(
            timetable_for_employee_on_date(
                employee=self.employee, day=date(2026, 3, 10)
            ),
            self.morning,
        )
        self.assertIsNone(
            timetable_for_employee_on_date(employee=self.employee, day=date(2026, 3, 8))
        )
        self.assertIsNone(
            timetable_for_employee_on_date(
                employee=self.employee, day=date(2026, 3, 11)
            )
        )

    def test_day_cycle_alternates_by_offset_from_start_date(self):
        self.assign_week(
            code="SH-DAYCYC",
            employee=self.employee,
            start_date=self.monday,
            cycle_unit="day",
            shift_days=[
                {"day_number": 1, "timetable": self.night},
                {"day_number": 2, "timetable": self.morning},
            ],
        )

        self.assertEqual(
            timetable_for_employee_on_date(
                employee=self.employee, day=date(2026, 3, 9)
            ),
            self.night,
        )
        self.assertEqual(
            timetable_for_employee_on_date(
                employee=self.employee, day=date(2026, 3, 10)
            ),
            self.morning,
        )
        self.assertEqual(
            timetable_for_employee_on_date(
                employee=self.employee, day=date(2026, 3, 11)
            ),
            self.night,
        )

    def test_two_week_cycle(self):
        self.assign_week(
            code="SH-2WK",
            employee=self.employee,
            start_date=self.monday,
            cycle_count=2,
            shift_days=[
                {
                    "day_number": day_number,
                    "timetable": self.morning if day_number <= 7 else self.night,
                }
                for day_number in range(1, 15)
            ],
        )

        # Week one Monday -> morning, week two Monday -> night, then back.
        self.assertEqual(
            timetable_for_employee_on_date(
                employee=self.employee, day=date(2026, 3, 9)
            ),
            self.morning,
        )
        self.assertEqual(
            timetable_for_employee_on_date(
                employee=self.employee, day=date(2026, 3, 16)
            ),
            self.night,
        )
        self.assertEqual(
            timetable_for_employee_on_date(
                employee=self.employee, day=date(2026, 3, 23)
            ),
            self.morning,
        )

    def test_shift_without_days_resolves_to_none(self):
        self.assign_week(
            code="SH-EMPTY",
            employee=self.employee,
            shift_days=[],
        )

        resolved = timetable_for_employee_on_date(
            employee=self.employee, day=self.monday
        )

        self.assertIsNone(resolved)

    def test_full_workweek_rotation_resolves_weekend_to_off_timetable(self):
        self.assign_week(
            code="SH-WEEK7",
            employee=self.employee,
            shift_days=[
                {"day_number": day_number, "timetable": self.morning}
                for day_number in range(1, 6)
            ]
            + [
                {"day_number": day_number, "timetable": self.day_off}
                for day_number in (6, 7)
            ],
        )

        # Mon 2026-03-09 through Sun 2026-03-15.
        expected = [
            (date(2026, 3, 9), self.morning),
            (date(2026, 3, 10), self.morning),
            (date(2026, 3, 11), self.morning),
            (date(2026, 3, 12), self.morning),
            (date(2026, 3, 13), self.morning),
            (date(2026, 3, 14), self.day_off),
            (date(2026, 3, 15), self.day_off),
        ]
        for day, timetable in expected:
            with self.subTest(day=day):
                self.assertEqual(
                    timetable_for_employee_on_date(employee=self.employee, day=day),
                    timetable,
                )

    def test_department_assignment_for_other_department_does_not_apply(self):
        own_department = department_factory(name="Ops", code="OPS-OWN")
        other_department = department_factory(name="Finance", code="FIN-OTHER")
        employee = employee_factory(
            first_name="CrossDept", emp_code="E503", department=own_department
        )
        self.assign_week(
            code="SH-FIN",
            department=other_department,
            shift_days=[{"day_number": 1, "timetable": self.morning}],
        )

        resolved = timetable_for_employee_on_date(employee=employee, day=self.monday)

        self.assertIsNone(resolved)

    def test_employee_without_department_ignores_department_assignments(self):
        department = department_factory(name="AnyDept", code="ANY")
        employee = employee_factory(first_name="NoDept", emp_code="E504")
        self.assign_week(
            code="SH-NODEPT",
            department=department,
            shift_days=[{"day_number": 1, "timetable": self.morning}],
        )

        resolved = timetable_for_employee_on_date(employee=employee, day=self.monday)

        self.assertIsNone(resolved)

    def test_night_shift_resolution_feeds_expected_datetimes(self):
        """Monday night shift: expected out lands on Tuesday morning."""
        self.assign_week(
            code="SH-NIGHT",
            employee=self.employee,
            shift_days=[{"day_number": 1, "timetable": self.night}],
        )

        resolved = timetable_for_employee_on_date(
            employee=self.employee, day=self.monday
        )
        expected_in, expected_out = expected_datetimes(
            timetable=resolved, day=self.monday
        )

        self.assertEqual(resolved, self.night)
        self.assertEqual(timezone.localtime(expected_in).date(), date(2026, 3, 9))
        self.assertEqual(timezone.localtime(expected_out).date(), date(2026, 3, 10))
        self.assertEqual(timezone.localtime(expected_out).time(), time(6, 0))
