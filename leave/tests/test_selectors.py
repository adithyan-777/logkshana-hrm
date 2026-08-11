from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    employee_factory,
    holiday_factory,
    leave_policy_factory,
    leave_request_factory,
    leave_type_factory,
)
from leave.models import Holiday, LeaveType
from leave.selectors import (
    holiday_list,
    leave_policy_list,
    leave_request_list,
    leave_type_list,
)


class LeaveTypeListTests(BaseTenantTestCase):
    def test_returns_leave_types_ordered_by_name(self):
        leave_type_factory(name="Sick Leave", code="SICK")
        leave_type_factory(name="Annual Leave", code="ANNUAL")

        results = list(leave_type_list())

        self.assertEqual([lt.code for lt in results], ["ANNUAL", "SICK"])

    def test_filters_by_search(self):
        leave_type_factory(name="Annual Leave", code="ANNUAL")
        leave_type_factory(name="Sick Leave", code="SICK")

        results = list(leave_type_list(search="sick"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "SICK")

    def test_excludes_soft_deleted_leave_types(self):
        leave_type = leave_type_factory(name="Deleted", code="DEL")
        leave_type.delete()

        self.assertEqual(leave_type_list().count(), 0)
        self.assertEqual(LeaveType.all_objects.count(), 1)


class LeavePolicyListTests(BaseTenantTestCase):
    def test_filters_by_leave_type_name(self):
        leave_type = leave_type_factory(name="Maternity", code="MAT")
        leave_policy_factory(name="Standard Maternity", leave_type=leave_type)
        leave_policy_factory(name="Other Policy", leave_type=leave_type_factory(name="Other", code="OTH"))

        results = list(leave_policy_list(search="maternity"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Standard Maternity")


class LeaveRequestListTests(BaseTenantTestCase):
    def test_filters_by_employee_name(self):
        employee = employee_factory(first_name="Searchable", emp_code="LR200")
        leave_request_factory(employee=employee, reason="Vacation")
        leave_request_factory(
            employee=employee_factory(first_name="Other", emp_code="LR201"),
        )

        results = list(leave_request_list(search="searchable"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].employee, employee)

    def test_filters_by_status(self):
        leave_request_factory(
            employee=employee_factory(first_name="Pending", emp_code="LR202"),
            status="pending",
        )

        results = list(leave_request_list(search="pending"))

        self.assertEqual(len(results), 1)


class HolidayListTests(BaseTenantTestCase):
    def test_filters_by_name(self):
        holiday_factory(name="Eid Al Fitr")
        holiday_factory(name="New Year")

        results = list(holiday_list(search="eid"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Eid Al Fitr")

    def test_excludes_soft_deleted_holidays(self):
        holiday = holiday_factory(name="Removed", date="2026-2-1")
        holiday.delete()

        self.assertEqual(holiday_list().count(), 0)
        self.assertEqual(Holiday.all_objects.count(), 1)
