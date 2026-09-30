"""Tests for AttendanceActivity -> Attendance linkage.

``is_attendance_processed`` is now a read-only alias for
``attendance_id is not None``: the FK is the only source of truth, so
the flag can't drift from the real linkage.
"""

from datetime import date, datetime

from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity
from attendance.recalculation import recalculate_attendance
from attendance.services import activity_create, activity_update
from common.tests.base import BaseTenantTestCase
from common.tests.factories import employee_factory, schedule_factory
from schedule.models import EmployeeScheduleAssignment


def _punch(*, employee, day, hour, minute=0, **kwargs):
    kwargs.setdefault("recalculate", False)
    return activity_create(
        employee=employee,
        punch_time=datetime(
            day.year,
            day.month,
            day.day,
            hour,
            minute,
            tzinfo=timezone.get_current_timezone(),
        ),
        **kwargs,
    )


def _assign(*, employee, day):
    schedule = schedule_factory(name="Processed Sched")
    assignment = EmployeeScheduleAssignment.objects.create(
        schedule=schedule,
        start_date=day.replace(day=1),
        end_date=None,
    )
    assignment.employees.add(employee)
    return assignment


class AttendanceProcessedFlagTests(BaseTenantTestCase):
    def test_unconsumed_punch_is_unprocessed(self):
        employee = employee_factory(first_name="Bio", emp_code="PRC001")
        punch = _punch(employee=employee, day=date(2026, 9, 24), hour=9)

        self.assertIsNone(punch.attendance_id)
        self.assertFalse(punch.is_attendance_processed)

    def test_manual_punch_still_needs_a_day_row(self):
        employee = employee_factory(first_name="Manual", emp_code="PRC002")
        punch = _punch(
            employee=employee,
            day=date(2026, 9, 24),
            hour=9,
            method=AttendanceActivity.AttendanceActivityMethodType.MANUAL,
        )

        self.assertIsNone(punch.attendance_id)
        self.assertFalse(punch.is_attendance_processed)

    def test_punch_marked_when_consumed_by_recalculation(self):
        day = date(2026, 9, 24)
        employee = employee_factory(first_name="Consumed", emp_code="PRC003")
        _assign(employee=employee, day=day)

        punch = _punch(employee=employee, day=day, hour=9)
        self.assertFalse(punch.is_attendance_processed)

        recalculate_attendance(employee=employee, day=day)

        punch.refresh_from_db()
        self.assertIsNotNone(punch.attendance_id)
        self.assertTrue(punch.is_attendance_processed)

    def test_flag_cleared_when_row_has_no_punches_left(self):
        day = date(2026, 9, 25)
        employee = employee_factory(first_name="Cleared", emp_code="PRC004")
        _assign(employee=employee, day=day)

        punch = _punch(employee=employee, day=day, hour=9)
        row = recalculate_attendance(employee=employee, day=day)
        punch.refresh_from_db()
        self.assertEqual(punch.attendance_id, row.pk)

        # Move the punch to another day: the original row now has no
        # punches, so it must unlink and fall back to an empty day.
        activity_update(
            activity=punch,
            employee=employee,
            punch_time=datetime(
                2026, 9, 26, 9, tzinfo=timezone.get_current_timezone()
            ),
            direction=AttendanceActivity.Direction.IN,
            method=AttendanceActivity.AttendanceActivityMethodType.MANUAL,
        )

        punch.refresh_from_db()
        self.assertNotEqual(punch.attendance_id, row.pk)
        row.refresh_from_db()
        self.assertIsNone(row.check_in)
        self.assertEqual(row.status, Attendance.Status.ABSENT)
