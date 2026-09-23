from django.core.exceptions import ValidationError
from django.utils import timezone

from attendance.models import AttendanceActivity
from common.tests.base import BaseTenantTestCase
from common.tests.factories import device_factory, employee_factory
from companies.models import Branch
from companies.services import (
    PRIMARY_BRANCH_CODE,
    PRIMARY_BRANCH_NAME,
    attendance_log_create,
    branch_create,
    companies_ensure_primary_branches,
    company_primary_branch_get_or_create,
)


class BranchCreateTests(BaseTenantTestCase):
    def test_creates_branch_for_company(self):
        branch = branch_create(name="HQ", company=self.tenant, code="HQ")

        self.assertEqual(branch.name, "HQ")
        self.assertEqual(branch.code, "HQ")
        self.assertEqual(branch.company_id, self.tenant.id)


class CompanyPrimaryBranchTests(BaseTenantTestCase):
    def test_creates_primary_branch_when_missing(self):
        branch, created = company_primary_branch_get_or_create(company=self.tenant)

        self.assertTrue(created)
        self.assertEqual(branch.name, PRIMARY_BRANCH_NAME)
        self.assertEqual(branch.code, PRIMARY_BRANCH_CODE)
        self.assertEqual(branch.company_id, self.tenant.id)

    def test_returns_existing_primary_branch(self):
        first, created_first = company_primary_branch_get_or_create(company=self.tenant)
        second, created_second = company_primary_branch_get_or_create(
            company=self.tenant
        )

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            Branch.objects.filter(
                company=self.tenant, name=PRIMARY_BRANCH_NAME
            ).count(),
            1,
        )


class CompaniesEnsurePrimaryBranchesTests(BaseTenantTestCase):
    def test_assigns_primary_branch_to_employees_without_one(self):
        employee = employee_factory(
            first_name="No", last_name="Branch", emp_code="NB001"
        )
        self.assertIsNone(employee.branch_id)

        results = companies_ensure_primary_branches(companies=[self.tenant])

        employee.refresh_from_db()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["branch_created"])
        self.assertEqual(results[0]["employees_updated"], 1)
        self.assertEqual(employee.branch_id, results[0]["branch"].id)

    def test_does_not_overwrite_existing_employee_branch(self):
        other_branch = branch_create(name="other", company=self.tenant, code="OTHER")
        employee = employee_factory(
            first_name="Has", last_name="Branch", emp_code="HB001"
        )
        employee.branch = other_branch
        employee.save(update_fields=["branch"])

        results = companies_ensure_primary_branches(companies=[self.tenant])

        employee.refresh_from_db()
        self.assertEqual(results[0]["employees_updated"], 0)
        self.assertEqual(employee.branch_id, other_branch.id)

    def test_is_idempotent(self):
        employee_factory(first_name="Once", last_name="Assigned", emp_code="OA001")

        first = companies_ensure_primary_branches(companies=[self.tenant])
        second = companies_ensure_primary_branches(companies=[self.tenant])

        self.assertTrue(first[0]["branch_created"])
        self.assertFalse(second[0]["branch_created"])
        self.assertEqual(first[0]["employees_updated"], 1)
        self.assertEqual(second[0]["employees_updated"], 0)
        self.assertEqual(
            Branch.objects.filter(
                company=self.tenant, name=PRIMARY_BRANCH_NAME
            ).count(),
            1,
        )


class AttendanceLogCreateTests(BaseTenantTestCase):
    def test_creates_biometric_punch(self):
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee = employee_factory(first_name="Alice", emp_code="E001")
        timestamp = timezone.now()

        punch = attendance_log_create(
            serial_number="ZK-001",
            employee_id="E001",
            timestamp=timestamp,
        )

        self.assertEqual(punch.employee, employee)
        self.assertEqual(
            punch.method, AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC
        )
        self.assertEqual(punch.direction, AttendanceActivity.Direction.UNKNOWN)
        self.assertEqual(punch.punch_time, timestamp)
        self.assertEqual(
            punch.external_id,
            f"device:ZK-001:E001:{timestamp.isoformat()}",
        )
        self.assertEqual(
            AttendanceActivity.objects.filter(employee=employee).count(),
            1,
        )

    def test_rejects_unknown_serial(self):
        employee_factory(first_name="Alice", emp_code="E001")

        with self.assertRaises(ValidationError) as ctx:
            attendance_log_create(
                serial_number="MISSING",
                employee_id="E001",
                timestamp=timezone.now(),
            )

        self.assertIn("serial_number", ctx.exception.message_dict)
        self.assertEqual(AttendanceActivity.objects.count(), 0)

    def test_rejects_inactive_device(self):
        device_factory(serial_number="ZK-OFF", company=self.tenant, is_active=False)
        employee_factory(first_name="Alice", emp_code="E001")

        with self.assertRaises(ValidationError) as ctx:
            attendance_log_create(
                serial_number="ZK-OFF",
                employee_id="E001",
                timestamp=timezone.now(),
            )

        self.assertIn("serial_number", ctx.exception.message_dict)
        self.assertEqual(AttendanceActivity.objects.count(), 0)

    def test_rejects_unknown_emp_code(self):
        device_factory(serial_number="ZK-001", company=self.tenant)

        with self.assertRaises(ValidationError) as ctx:
            attendance_log_create(
                serial_number="ZK-001",
                employee_id="MISSING",
                timestamp=timezone.now(),
            )

        self.assertIn("employee_id", ctx.exception.message_dict)
        self.assertEqual(AttendanceActivity.objects.count(), 0)

    def test_rejects_inactive_employee(self):
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee_factory(first_name="Gone", emp_code="E001", is_active=False)

        with self.assertRaises(ValidationError) as ctx:
            attendance_log_create(
                serial_number="ZK-001",
                employee_id="E001",
                timestamp=timezone.now(),
            )

        self.assertIn("employee_id", ctx.exception.message_dict)
        self.assertEqual(AttendanceActivity.objects.count(), 0)

    def test_rejects_duplicate_emp_code(self):
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee_factory(first_name="One", last_name="Dup", emp_code="DUP")
        employee_factory(first_name="Two", last_name="Dup", emp_code="DUP")

        with self.assertRaises(ValidationError) as ctx:
            attendance_log_create(
                serial_number="ZK-001",
                employee_id="DUP",
                timestamp=timezone.now(),
            )

        self.assertIn("employee_id", ctx.exception.message_dict)
        self.assertEqual(AttendanceActivity.objects.count(), 0)

    def test_replay_returns_existing_punch(self):
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee_factory(first_name="Alice", emp_code="E001")
        timestamp = timezone.now()

        first = attendance_log_create(
            serial_number="ZK-001",
            employee_id="E001",
            timestamp=timestamp,
        )
        second = attendance_log_create(
            serial_number="ZK-001",
            employee_id="E001",
            timestamp=timestamp,
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(AttendanceActivity.objects.count(), 1)
