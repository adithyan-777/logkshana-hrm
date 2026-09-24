"""Tests for AttendanceActivity.is_attendance_processed."""

from datetime import date, datetime

from django.utils import timezone

from attendance.models import AttendanceActivity
from attendance.recalculation import recalculate_attendance
from attendance.services import activity_create
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


class AttendanceProcessedFlagTests(BaseTenantTestCase):
    def test_biometric_punch_born_unprocessed(self):
        employee = employee_factory(first_name="Bio", emp_code="PRC001")
        punch = _punch(employee=employee, day=date(2026, 9, 24), hour=9)

        self.assertFalse(punch.is_attendance_processed)

    def test_manual_punch_born_processed(self):
        employee = employee_factory(first_name="Manual", emp_code="PRC002")
        punch = _punch(
            employee=employee,
            day=date(2026, 9, 24),
            hour=9,
            method=AttendanceActivity.AttendanceActivityMethodType.MANUAL,
        )

        self.assertTrue(punch.is_attendance_processed)

    def test_punch_marked_when_consumed_by_recalculation(self):
        day = date(2026, 9, 24)
        employee = employee_factory(first_name="Consumed", emp_code="PRC003")
        schedule = schedule_factory(name="Processed Sched")
        assignment = EmployeeScheduleAssignment.objects.create(
            schedule=schedule,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
        )
        assignment.employees.add(employee)

        punch = _punch(employee=employee, day=day, hour=9)
        self.assertFalse(punch.is_attendance_processed)

        recalculate_attendance(employee=employee, day=day)

        punch.refresh_from_db()
        self.assertTrue(punch.is_attendance_processed)
