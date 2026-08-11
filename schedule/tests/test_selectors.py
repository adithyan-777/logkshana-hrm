from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    department_factory,
    employee_factory,
    shift_factory,
    timetable_factory,
)
from schedule.models import ScheduleAssignment, Timetable
from schedule.selectors import (
    schedule_assignment_list,
    shift_list,
    temporary_schedule_list,
    timetable_list,
)
from schedule.services import schedule_assignment_create, temporary_schedule_create


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
