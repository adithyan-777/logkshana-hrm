from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    employee_factory,
    holiday_factory,
    leave_policy_factory,
    leave_request_factory,
    leave_type_factory,
)
from leave.models import Holiday, LeavePolicy, LeaveRequest, LeaveType
from leave.services import (
    holiday_create,
    leave_policy_create,
    leave_request_create,
    leave_type_create,
)


class LeaveTypeCreateTests(BaseTenantTestCase):
    def test_creates_leave_type(self):
        leave_type = leave_type_create(
            name="Annual Leave",
            code="ANNUAL",
            description="Paid annual leave",
        )

        self.assertEqual(leave_type.name, "Annual Leave")
        self.assertTrue(leave_type.paid)
        self.assertTrue(LeaveType.objects.filter(code="ANNUAL").exists())

    def test_rejects_duplicate_code(self):
        leave_type_create(name="Annual", code="ANNUAL")

        with self.assertRaises((ValidationError, IntegrityError)):
            leave_type_create(name="Annual Copy", code="ANNUAL")


class LeavePolicyCreateTests(BaseTenantTestCase):
    def test_creates_leave_policy(self):
        leave_type = leave_type_factory(name="Annual", code="ANN-POL")
        policy = leave_policy_create(
            leave_type=leave_type,
            name="Standard Annual",
            entitlement_days=30,
            accrual_type=LeavePolicy.AccrualType.YEARLY,
            carry_forward=True,
            max_carry_forward_days=5,
        )

        self.assertEqual(policy.leave_type, leave_type)
        self.assertEqual(policy.entitlement_days, 30)
        self.assertTrue(policy.carry_forward)


class LeaveRequestCreateTests(BaseTenantTestCase):
    def test_creates_leave_request(self):
        employee = employee_factory(first_name="Alice", emp_code="LR100")
        leave_type = leave_type_factory(name="Sick", code="SICK-R")

        leave_request = leave_request_create(
            employee=employee,
            leave_type=leave_type,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 3),
            duration_type=LeaveRequest.DurationType.FULL_DAY,
            days=3,
            reason="Flu",
            status=LeaveRequest.Status.PENDING,
        )

        self.assertEqual(leave_request.employee, employee)
        self.assertEqual(leave_request.days, 3)
        self.assertEqual(leave_request.status, LeaveRequest.Status.PENDING)

    def test_rejects_end_date_before_start_date(self):
        employee = employee_factory(first_name="Bob", emp_code="LR101")
        leave_type = leave_type_factory(name="Casual", code="CAS-R")

        with self.assertRaises(ValidationError):
            leave_request_create(
                employee=employee,
                leave_type=leave_type,
                start_date=date(2026, 5, 10),
                end_date=date(2026, 5, 1),
                duration_type=LeaveRequest.DurationType.FULL_DAY,
                days=1,
            )


class HolidayCreateTests(BaseTenantTestCase):
    def test_creates_holiday(self):
        holiday = holiday_create(
            name="National Day",
            date=date(2026, 12, 18),
            holiday_type=Holiday.HolidayType.PUBLIC,
            description="Qatar National Day",
        )

        self.assertEqual(holiday.name, "National Day")
        self.assertEqual(holiday.get_holiday_type_display(), "Public Holiday")

    def test_rejects_end_date_before_start_date(self):
        with self.assertRaises(ValidationError):
            holiday_create(
                name="Bad Range",
                date=date(2026, 6, 10),
                end_date=date(2026, 6, 1),
                holiday_type=Holiday.HolidayType.COMPANY,
            )


class LeaveModelTests(BaseTenantTestCase):
    def test_soft_delete_excludes_leave_type_from_default_manager(self):
        leave_type = leave_type_factory(name="Deleted", code="DEL-LT")
        leave_type.delete()

        self.assertEqual(LeaveType.objects.count(), 0)
        self.assertEqual(LeaveType.all_objects.count(), 1)

    def test_leave_request_factory_defaults(self):
        leave_request = leave_request_factory()

        self.assertEqual(leave_request.status, LeaveRequest.Status.PENDING)
        self.assertEqual(leave_request.days, 3)
