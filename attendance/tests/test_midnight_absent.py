"""Tests for the auto-ABSENT midnight job (cron + tenant actor)."""

from datetime import date, datetime
from unittest.mock import patch

from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity
from attendance.services import (
    attendance_absent_rows_ensure,
    employees_absent_condition,
)
from attendance.tasks import fanout_mark_absent_for_today, mark_absent_for_tenant
from common.tests.base import BaseTenantTestCase
from common.tests.factories import employee_factory

DAY = date(2026, 11, 2)


def _punch_time(day, hour=9, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute,
                    tzinfo=timezone.get_current_timezone())


class EmployeesAbsentConditionTests(BaseTenantTestCase):
    def _punch(self, employee, at, direction):
        return AttendanceActivity.objects.create(
            employee=employee, punch_time=at, direction=direction
        )

    def test_active_employee_without_punches_is_included(self):
        employee = employee_factory(first_name="Eve", emp_code="ABS001")

        self.assertIn(employee, employees_absent_condition(day=DAY))

    def test_employee_punched_out_before_the_day_is_included(self):
        employee = employee_factory(first_name="Out", emp_code="ABS002")
        self._punch(
            employee, _punch_time(date(2026, 11, 1), 8), AttendanceActivity.Direction.IN
        )
        self._punch(
            employee,
            _punch_time(date(2026, 11, 1), 17),
            AttendanceActivity.Direction.OUT,
        )

        self.assertIn(employee, employees_absent_condition(day=DAY))

    def test_employee_last_punched_in_is_excluded(self):
        # Overnight shift: checked in yesterday evening, never checked
        # out — might still be in the building at midnight.
        employee = employee_factory(first_name="Night", emp_code="ABS003")
        self._punch(
            employee,
            _punch_time(date(2026, 11, 1), 22),
            AttendanceActivity.Direction.IN,
        )

        self.assertNotIn(employee, employees_absent_condition(day=DAY))

    def test_employee_last_punched_in_days_ago_is_excluded(self):
        # Last known state IN, whenever it was — cannot be sure they
        # left the building.
        employee = employee_factory(first_name="Stale", emp_code="ABS004")
        self._punch(
            employee,
            _punch_time(date(2026, 10, 30), 9),
            AttendanceActivity.Direction.IN,
        )

        self.assertNotIn(employee, employees_absent_condition(day=DAY))

    def test_employee_last_punch_unknown_direction_is_excluded(self):
        employee = employee_factory(first_name="Unknown", emp_code="ABS005")
        self._punch(
            employee,
            _punch_time(date(2026, 11, 1), 10),
            AttendanceActivity.Direction.UNKNOWN,
        )

        self.assertNotIn(employee, employees_absent_condition(day=DAY))

    def test_employee_with_punch_that_day_is_excluded(self):
        employee = employee_factory(first_name="In", emp_code="ABS006")
        self._punch(employee, _punch_time(DAY, 8, 55), AttendanceActivity.Direction.IN)

        self.assertNotIn(employee, employees_absent_condition(day=DAY))

    def test_employee_with_row_that_day_is_excluded(self):
        employee = employee_factory(first_name="Row", emp_code="ABS007")
        Attendance.objects.create(employee=employee, day=DAY)

        self.assertNotIn(employee, employees_absent_condition(day=DAY))

    def test_inactive_employee_is_excluded(self):
        employee_factory(first_name="Off", emp_code="ABS008", is_active=False)

        self.assertFalse(
            employees_absent_condition(day=DAY).filter(emp_code="ABS008").exists()
        )


class AttendanceAbsentRowsEnsureTests(BaseTenantTestCase):
    def test_creates_absent_row_for_eligible_employee(self):
        employee = employee_factory(first_name="New", emp_code="ENS001")

        rows = attendance_absent_rows_ensure(day=DAY)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.employee, employee)
        self.assertEqual(row.day, DAY)
        self.assertEqual(row.status, Attendance.Status.ABSENT)
        self.assertFalse(row.is_calculated)
        self.assertIsNone(row.check_in)
        self.assertIsNone(row.check_out)

    def test_idempotent_on_rerun(self):
        employee_factory(first_name="Again", emp_code="ENS002")

        first = attendance_absent_rows_ensure(day=DAY)
        second = attendance_absent_rows_ensure(day=DAY)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(Attendance.objects.filter(day=DAY).count(), 1)

    def test_existing_row_is_never_overwritten(self):
        employee = employee_factory(first_name="Keep", emp_code="ENS003")
        Attendance.objects.create(
            employee=employee, day=DAY, status=Attendance.Status.PRESENT
        )

        attendance_absent_rows_ensure(day=DAY)

        row = Attendance.objects.get(employee=employee, day=DAY)
        self.assertEqual(row.status, Attendance.Status.PRESENT)


class MidnightTaskTests(BaseTenantTestCase):
    def test_fanout_enqueues_one_task_per_tenant(self):
        with patch("attendance.tasks.mark_absent_for_tenant") as mock_actor:
            fanout_mark_absent_for_today()

        schemas = [call.args[0] for call in mock_actor.send.call_args_list]
        self.assertNotIn("public", schemas)
        self.assertIn(self.tenant.schema_name, schemas)
        self.assertEqual(len(schemas), len(set(schemas)))

    def test_tenant_actor_creates_absent_rows(self):
        employee = employee_factory(first_name="Mid", emp_code="MID001")

        result = mark_absent_for_tenant(self.tenant.schema_name, DAY.isoformat())

        self.assertEqual(result["created"], 1)
        row = Attendance.objects.get(employee=employee, day=DAY)
        self.assertEqual(row.status, Attendance.Status.ABSENT)
        self.assertFalse(row.is_calculated)

    def test_tenant_actor_is_idempotent(self):
        employee_factory(first_name="Twice", emp_code="MID002")

        mark_absent_for_tenant(self.tenant.schema_name, DAY.isoformat())
        result = mark_absent_for_tenant(self.tenant.schema_name, DAY.isoformat())

        self.assertEqual(result["created"], 0)
