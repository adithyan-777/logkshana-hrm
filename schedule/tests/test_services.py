from datetime import date, time

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    assignment_dates,
    department_factory,
    employee_factory,
    shift_factory,
    timetable_factory,
)
from schedule.models import ScheduleAssignment, ShiftDay, Timetable
from schedule.services import (
    schedule_assignment_create,
    shift_create,
    temporary_schedule_create,
    timetable_create,
)


class TimetableCreateTests(BaseTenantTestCase):
    def test_creates_timetable_with_defaults(self):
        timetable = timetable_create(
            name="Morning",
            code="MORN",
            type=Timetable.Type.NORMAL,
            work_type=Timetable.WorkType.WORK,
            check_in=time(9, 0),
            check_out=time(18, 0),
        )

        self.assertEqual(timetable.name, "Morning")
        self.assertEqual(timetable.day_change_time, time(8, 0))
        self.assertTrue(Timetable.objects.filter(code="MORN").exists())

    def test_rejects_duplicate_code(self):
        timetable_create(
            name="Morning",
            code="MORN",
            type=Timetable.Type.NORMAL,
            work_type=Timetable.WorkType.WORK,
        )

        with self.assertRaises((ValidationError, IntegrityError)):
            timetable_create(
                name="Morning Copy",
                code="MORN",
                type=Timetable.Type.NORMAL,
                work_type=Timetable.WorkType.WORK,
            )

    def test_rejects_overnight_shift_without_cross_days(self):
        with self.assertRaises(ValidationError) as context:
            timetable_create(
                name="Night",
                code="NIGHT-VAL",
                type=Timetable.Type.NORMAL,
                work_type=Timetable.WorkType.WORK,
                check_in=time(22, 0),
                check_out=time(6, 0),
                check_in_cross_days=0,
                check_out_cross_days=0,
            )

        self.assertIn("check_out_cross_days", context.exception.message_dict)
        self.assertFalse(Timetable.objects.filter(code="NIGHT-VAL").exists())

    def test_creates_overnight_shift_with_cross_days(self):
        timetable = timetable_create(
            name="Night",
            code="NIGHT-OK",
            type=Timetable.Type.NORMAL,
            work_type=Timetable.WorkType.WORK,
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )

        self.assertEqual(timetable.check_out_cross_days, 1)
        self.assertEqual(timetable.check_in, time(22, 0))
        self.assertEqual(timetable.check_out, time(6, 0))

    def test_rejects_check_in_cross_days_pushing_in_past_out(self):
        # 09:00 pushed to the next day can no longer precede a
        # same-day 18:00 check-out.
        with self.assertRaises(ValidationError):
            timetable_create(
                name="Skewed",
                code="SKEW",
                type=Timetable.Type.NORMAL,
                work_type=Timetable.WorkType.WORK,
                check_in=time(9, 0),
                check_out=time(18, 0),
                check_in_cross_days=1,
                check_out_cross_days=0,
            )


class ShiftCreateTests(BaseTenantTestCase):
    def test_creates_shift_with_days(self):
        timetable = timetable_factory(name="Morning", code="MORN-S")
        shift = shift_create(
            name="Weekly",
            code="WEEK",
            cycle_unit="week",
            shift_days=[{"day_number": 1, "timetable": timetable}],
        )

        self.assertEqual(shift.days.count(), 1)
        self.assertEqual(shift.days.first().timetable, timetable)

    def test_rejects_duplicate_day_number(self):
        timetable = timetable_factory(name="Morning", code="MORN-D")
        shift = shift_factory(name="Weekly", code="WEEK-D", timetable=timetable)

        with self.assertRaises((ValidationError, IntegrityError)):
            ShiftDay.objects.create(shift=shift, day_number=1, timetable=timetable)


class ScheduleAssignmentCreateTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.shift = shift_factory(name="Weekly", code="WEEK-A")
        self.start_date, self.end_date = assignment_dates()

    def test_creates_employee_assignment(self):
        employee = employee_factory(first_name="Jane", emp_code="E100")
        assignment = schedule_assignment_create(
            assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
            shift=self.shift,
            start_date=self.start_date,
            end_date=self.end_date,
            employee=employee,
        )

        self.assertEqual(assignment.employee, employee)
        self.assertIsNone(assignment.department)

    def test_creates_department_assignment(self):
        department = department_factory(name="HR", code="HR")
        assignment = schedule_assignment_create(
            assignment_type=ScheduleAssignment.AssignmentType.DEPARTMENT,
            shift=self.shift,
            start_date=self.start_date,
            end_date=self.end_date,
            department=department,
        )

        self.assertEqual(assignment.department, department)
        self.assertIsNone(assignment.employee)

    def test_rejects_end_date_before_start_date(self):
        employee = employee_factory(first_name="John", emp_code="E101")

        with self.assertRaises(ValidationError):
            schedule_assignment_create(
                assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
                shift=self.shift,
                start_date=date(2026, 12, 31),
                end_date=date(2026, 1, 1),
                employee=employee,
            )

    def test_requires_employee_for_employee_assignment(self):
        with self.assertRaises(ValidationError):
            schedule_assignment_create(
                assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
                shift=self.shift,
                start_date=self.start_date,
                end_date=self.end_date,
            )


class TemporaryScheduleCreateTests(BaseTenantTestCase):
    def test_creates_temporary_schedule(self):
        employee = employee_factory(first_name="Temp", emp_code="E200")
        timetable = timetable_factory(name="Overtime", code="OT")

        temporary = temporary_schedule_create(
            employee=employee,
            date=date(2026, 6, 1),
            timetable=timetable,
            reason="Weekend work",
        )

        self.assertEqual(temporary.reason, "Weekend work")
        self.assertTrue(temporary.overrides_normal_schedule)

    def test_rejects_duplicate_employee_date_timetable(self):
        employee = employee_factory(first_name="Dup", emp_code="E201")
        timetable = timetable_factory(name="Cover", code="DUP")

        temporary_schedule_create(
            employee=employee,
            date=date(2026, 6, 2),
            timetable=timetable,
        )

        with self.assertRaises((ValidationError, IntegrityError)):
            temporary_schedule_create(
                employee=employee,
                date=date(2026, 6, 2),
                timetable=timetable,
            )
