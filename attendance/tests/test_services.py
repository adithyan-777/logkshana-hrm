from datetime import date

from django.db import IntegrityError
from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity
from attendance.services import activity_create, attendance_record_create
from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    activity_factory,
    attendance_record_factory,
    employee_factory,
)


class AttendanceActivityCreateTests(BaseTenantTestCase):
    def test_creates_activity(self):
        employee = employee_factory(first_name="Alice", emp_code="AT100")
        punch_time = timezone.now()

        activity = activity_create(
            employee=employee,
            external_id="EXT-001",
            punch_time=punch_time,
            direction=AttendanceActivity.Direction.IN,
            method=AttendanceActivity.AttendanceActivityMethodType.MANUAL,
        )

        self.assertEqual(activity.employee, employee)
        self.assertEqual(activity.external_id, "EXT-001")
        self.assertTrue(
            AttendanceActivity.objects.filter(external_id="EXT-001").exists()
        )

    def test_generates_external_id_when_omitted(self):
        employee = employee_factory(first_name="Auto", emp_code="AT101")

        activity = activity_create(
            employee=employee,
            punch_time=timezone.now(),
            direction=AttendanceActivity.Direction.IN,
            method=AttendanceActivity.AttendanceActivityMethodType.MANUAL,
        )

        self.assertTrue(activity.external_id.startswith("manual:"))

    def test_repeating_external_id_returns_existing(self):
        employee = employee_factory(first_name="Dup", emp_code="AT102")

        first = activity_create(
            employee=employee,
            punch_time=timezone.now(),
            direction=AttendanceActivity.Direction.IN,
            method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
            external_id="gateway:999",
        )
        second = activity_create(
            employee=employee,
            punch_time=timezone.now(),
            direction=AttendanceActivity.Direction.IN,
            method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
            external_id="gateway:999",
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            AttendanceActivity.objects.filter(external_id="gateway:999").count(), 1
        )


class AttendanceRecordCreateTests(BaseTenantTestCase):
    def test_creates_manual_record(self):
        employee = employee_factory(first_name="Bob", emp_code="DA100")

        record = attendance_record_create(
            employee=employee,
            day=date(2026, 3, 1),
            status=Attendance.Status.PRESENT,
        )

        self.assertEqual(record.employee, employee)
        self.assertFalse(record.is_calculated)

    def test_rejects_duplicate_employee_day(self):
        employee = employee_factory(first_name="Dup", emp_code="DA101")
        attendance_record_create(
            employee=employee,
            day=date(2026, 3, 2),
            status=Attendance.Status.PRESENT,
        )

        with self.assertRaises(IntegrityError):
            Attendance.objects.create(
                employee=employee,
                day=date(2026, 3, 2),
                status=Attendance.Status.ABSENT,
            )


class AttendanceModelTests(BaseTenantTestCase):
    def test_soft_delete_excludes_activity(self):
        activity = activity_factory()
        activity.delete()

        self.assertEqual(AttendanceActivity.objects.count(), 0)
        self.assertEqual(AttendanceActivity.all_objects.count(), 1)

    def test_record_factory_builds_manual_row(self):
        record = attendance_record_factory(status=Attendance.Status.LEAVE)

        self.assertEqual(record.status, Attendance.Status.LEAVE)
        self.assertFalse(record.is_calculated)
