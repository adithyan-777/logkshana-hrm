from datetime import date

from attendance.models import Attendance, AttendanceActivity
from attendance.selectors import attendance_activity_list, attendance_list
from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    activity_factory,
    attendance_record_factory,
    employee_factory,
)


class AttendanceActivityListTests(BaseTenantTestCase):
    def test_filters_by_employee_name(self):
        employee = employee_factory(first_name="Searchable", emp_code="AT200")
        activity_factory(employee=employee, external_id="SEARCH-1")
        activity_factory(
            employee=employee_factory(first_name="Other", emp_code="AT201"),
            external_id="OTHER-1",
        )

        results = list(attendance_activity_list(search="searchable"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].employee, employee)

    def test_filters_to_one_employee(self):
        employee = employee_factory(first_name="Mine", emp_code="AT-MINE")
        activity_factory(employee=employee, external_id="MINE-1")
        activity_factory(
            employee=employee_factory(first_name="Theirs", emp_code="AT-THEIRS"),
            external_id="THEIRS-1",
        )

        results = list(attendance_activity_list(employee=employee))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].external_id, "MINE-1")

    def test_excludes_soft_deleted_activities(self):
        activity = activity_factory(external_id="DEL-1")
        activity.delete()

        self.assertEqual(attendance_activity_list().count(), 0)
        self.assertEqual(AttendanceActivity.all_objects.count(), 1)


class AttendanceListTests(BaseTenantTestCase):
    def test_filters_by_status(self):
        attendance_record_factory(
            employee=employee_factory(first_name="Present", emp_code="DA200"),
            day=date(2026, 5, 1),
            status=Attendance.Status.PRESENT,
        )
        attendance_record_factory(
            employee=employee_factory(first_name="Absent", emp_code="DA201"),
            day=date(2026, 5, 2),
            status=Attendance.Status.ABSENT,
        )

        results = list(attendance_list(search="absent"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, Attendance.Status.ABSENT)

    def test_filters_to_one_employee(self):
        employee = employee_factory(first_name="Mine", emp_code="DA-MINE")
        attendance_record_factory(
            employee=employee,
            day=date(2026, 8, 1),
            status=Attendance.Status.PRESENT,
        )
        attendance_record_factory(
            employee=employee_factory(first_name="Theirs", emp_code="DA-THEIRS"),
            day=date(2026, 8, 1),
            status=Attendance.Status.ABSENT,
        )

        results = list(attendance_list(employee=employee))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].employee, employee)
        self.assertEqual(results[0].status, Attendance.Status.PRESENT)
