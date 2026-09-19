from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    attendance_correction_factory,
    attendance_rule_factory,
    attendance_transaction_factory,
    daily_attendance_factory,
    employee_factory,
)
from attendance.models import (
    AttendanceCorrection,
    AttendanceRule,
    AttendanceTransaction,
    DailyAttendance,
)
from attendance.services import (
    attendance_correction_create,
    attendance_rule_create,
    attendance_transaction_create,
    daily_attendance_create,
)


class AttendanceTransactionCreateTests(BaseTenantTestCase):
    def test_creates_transaction(self):
        employee = employee_factory(first_name="Alice", emp_code="AT100")
        timestamp = timezone.now()

        transaction = attendance_transaction_create(
            employee=employee,
            external_id="EXT-001",
            timestamp=timestamp,
            direction=AttendanceTransaction.Direction.IN,
            source=AttendanceTransaction.Source.MANUAL,
        )

        self.assertEqual(transaction.employee, employee)
        self.assertEqual(transaction.external_id, "EXT-001")
        self.assertTrue(
            AttendanceTransaction.objects.filter(external_id="EXT-001").exists()
        )

    def test_derives_ids_from_employee_when_omitted(self):
        employee = employee_factory(first_name="Auto", emp_code="AT101")

        transaction = attendance_transaction_create(
            employee=employee,
            timestamp=timezone.now(),
            direction=AttendanceTransaction.Direction.IN,
            source=AttendanceTransaction.Source.MANUAL,
        )

        self.assertTrue(transaction.external_id.startswith("manual:"))
        self.assertEqual(transaction.external_employee_id, "AT101")


class DailyAttendanceCreateTests(BaseTenantTestCase):
    def test_creates_daily_record(self):
        employee = employee_factory(first_name="Bob", emp_code="DA100")

        daily = daily_attendance_create(
            employee=employee,
            date=date(2026, 3, 1),
            status=DailyAttendance.Status.PRESENT,
            worked_minutes=480,
            scheduled_minutes=480,
            has_check_in=True,
            has_check_out=True,
        )

        self.assertEqual(daily.employee, employee)
        self.assertEqual(daily.worked_minutes, 480)

    def test_rejects_duplicate_employee_date(self):
        employee = employee_factory(first_name="Dup", emp_code="DA101")
        daily_attendance_create(
            employee=employee,
            date=date(2026, 3, 2),
            status=DailyAttendance.Status.PRESENT,
        )

        with self.assertRaises((ValidationError, IntegrityError)):
            daily_attendance_create(
                employee=employee,
                date=date(2026, 3, 2),
                status=DailyAttendance.Status.ABSENT,
            )


class AttendanceCorrectionCreateTests(BaseTenantTestCase):
    def test_creates_correction(self):
        employee = employee_factory(first_name="Carol", emp_code="AC100")
        check_in = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)

        correction = attendance_correction_create(
            employee=employee,
            date=date(2026, 4, 1),
            reason="Missed punch",
            check_in=check_in,
        )

        self.assertEqual(correction.reason, "Missed punch")
        self.assertEqual(correction.status, AttendanceCorrection.Status.PENDING)

    def test_rejects_check_out_before_check_in(self):
        employee = employee_factory(first_name="Dan", emp_code="AC101")
        check_in = timezone.now()
        check_out = check_in - timedelta(hours=2)

        with self.assertRaises(ValidationError):
            attendance_correction_create(
                employee=employee,
                date=date(2026, 4, 2),
                reason="Invalid times",
                check_in=check_in,
                check_out=check_out,
            )


class AttendanceRuleCreateTests(BaseTenantTestCase):
    def test_creates_rule(self):
        rule = attendance_rule_create(
            name="Standard",
            late_grace_minutes=15,
            early_leave_grace_minutes=10,
        )

        self.assertEqual(rule.name, "Standard")
        self.assertTrue(rule.require_check_in)
        self.assertTrue(AttendanceRule.objects.filter(name="Standard").exists())


class AttendanceModelTests(BaseTenantTestCase):
    def test_soft_delete_excludes_transaction(self):
        transaction = attendance_transaction_factory()
        transaction.delete()

        self.assertEqual(AttendanceTransaction.objects.count(), 0)
        self.assertEqual(AttendanceTransaction.all_objects.count(), 1)
