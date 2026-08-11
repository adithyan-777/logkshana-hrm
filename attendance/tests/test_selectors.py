from datetime import date

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    attendance_correction_factory,
    attendance_rule_factory,
    attendance_transaction_factory,
    daily_attendance_factory,
    employee_factory,
)
from attendance.models import AttendanceTransaction, DailyAttendance
from attendance.selectors import (
    attendance_correction_list,
    attendance_rule_list,
    attendance_transaction_list,
    daily_attendance_list,
)


class AttendanceTransactionListTests(BaseTenantTestCase):
    def test_filters_by_employee_name(self):
        employee = employee_factory(first_name="Searchable", emp_code="AT200")
        attendance_transaction_factory(employee=employee, external_id="SEARCH-1")
        attendance_transaction_factory(
            employee=employee_factory(first_name="Other", emp_code="AT201"),
            external_id="OTHER-1",
        )

        results = list(attendance_transaction_list(search="searchable"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].employee, employee)

    def test_excludes_soft_deleted_transactions(self):
        transaction = attendance_transaction_factory(external_id="DEL-1")
        transaction.delete()

        self.assertEqual(attendance_transaction_list().count(), 0)
        self.assertEqual(AttendanceTransaction.all_objects.count(), 1)


class DailyAttendanceListTests(BaseTenantTestCase):
    def test_filters_by_status(self):
        daily_attendance_factory(
            employee=employee_factory(first_name="Present", emp_code="DA200"),
            date=date(2026, 5, 1),
            status=DailyAttendance.Status.PRESENT,
        )
        daily_attendance_factory(
            employee=employee_factory(first_name="Absent", emp_code="DA201"),
            date=date(2026, 5, 2),
            status=DailyAttendance.Status.ABSENT,
        )

        results = list(daily_attendance_list(search="absent"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, DailyAttendance.Status.ABSENT)


class AttendanceCorrectionListTests(BaseTenantTestCase):
    def test_filters_by_reason(self):
        attendance_correction_factory(reason="Device malfunction")
        attendance_correction_factory(
            employee=employee_factory(first_name="Other", emp_code="AC200"),
            reason="Travel",
        )

        results = list(attendance_correction_list(search="malfunction"))

        self.assertEqual(len(results), 1)


class AttendanceRuleListTests(BaseTenantTestCase):
    def test_filters_by_name(self):
        attendance_rule_factory(name="Strict Rule")
        attendance_rule_factory(name="Lenient Rule")

        results = list(attendance_rule_list(search="strict"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Strict Rule")
