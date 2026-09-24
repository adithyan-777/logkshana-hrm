"""End-to-end attendance flow: company -> owner -> employee -> punches ->
Attendance row -> list tables -> CSV/XLSX export -> employee self-service.
"""

from datetime import date, datetime, time

from django.urls import reverse
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.models import Attendance, AttendanceActivity
from attendance.services import activity_create
from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import employee_factory, schedule_factory, timetable_factory
from schedule.models import EmployeeScheduleAssignment

DAY = date(2026, 3, 9)  # a Monday


def aware_at(day: date, at: time) -> datetime:
    return timezone.make_aware(datetime.combine(day, at))


class AttendanceEndToEndTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        # --- Company & owner ------------------------------------------------
        self.company = self.tenant
        self.assertEqual(self.company.name, "Test Company")
        with schema_context(get_public_schema_name()):
            owner = self.company.owner
        self.assertIsNotNone(owner)
        self.assertIn(owner, self.company.members.all())

        # --- Employee --------------------------------------------------------
        self.employee = employee_factory(
            first_name="Sara",
            last_name="Flow",
            emp_code="E2E-001",
            email="sara.flow@example.com",
            mobile="+97433000991",
        )
        self.employee.user.set_password(TEST_PASSWORD)
        self.employee.user.save(update_fields=["password"])

        # --- Timetable + schedule + assignment --------------------------------
        self.timetable = timetable_factory(
            name="Office",
            code="E2E-OFF",
            check_in=time(9, 0),
            check_out=time(18, 0),
        )
        self.schedule = schedule_factory(name="E2E Week", timetable=self.timetable)
        self.assignment = EmployeeScheduleAssignment.objects.create(
            name="E2E assignment",
            schedule=self.schedule,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.assignment.employees.set([self.employee])

    def _punch_day(self):
        """Two punches (in 09:05, out 18:02); recalc runs automatically."""
        activity_create(
            employee=self.employee,
            punch_time=aware_at(DAY, time(9, 5)),
            direction=AttendanceActivity.Direction.IN,
            external_id="E2E-IN-001",
        )
        activity_create(
            employee=self.employee,
            punch_time=aware_at(DAY, time(18, 2)),
            direction=AttendanceActivity.Direction.OUT,
            external_id="E2E-OUT-001",
        )
        return Attendance.objects.get(employee=self.employee, day=DAY)

    def test_punches_produce_correct_attendance_row(self):
        row = self._punch_day()

        self.assertEqual(row.status, Attendance.Status.LATE)
        self.assertEqual(row.worked_minutes, 8 * 60 + 57)  # 09:05 -> 18:02
        self.assertEqual(row.late_minutes, 5)
        self.assertEqual(row.overtime_minutes, 0)
        self.assertEqual(row.shift, self.timetable)
        self.assertTrue(row.is_calculated)
        self.assertEqual(
            timezone.localtime(row.first_in).time(), time(9, 5)
        )
        self.assertEqual(
            timezone.localtime(row.last_out).time(), time(18, 2)
        )
        self.assertEqual(row.attendance_activities.count(), 2)
        self.assertTrue(row.has_check_in)
        self.assertTrue(row.has_check_out)

    def test_tables_display_the_data(self):
        self._punch_day()

        punch_response = self.client.get(reverse("attendance_transaction_list"))
        self.assertEqual(punch_response.status_code, 200)
        self.assertContains(punch_response, "Sara Flow")
        self.assertContains(punch_response, "E2E-IN-001")

        daily_response = self.client.get(reverse("daily_attendance_list"))
        self.assertEqual(daily_response.status_code, 200)
        self.assertContains(daily_response, "Sara Flow")

        punch_log = self.client.get(
            reverse("report_punch_log"),
            {"date_from": "2026-03-01", "date_to": "2026-03-31"},
        )
        self.assertEqual(punch_log.status_code, 200)
        self.assertContains(punch_log, "Sara Flow")

        summary = self.client.get(
            reverse("report_attendance_summary"),
            {"date_from": "2026-03-01", "date_to": "2026-03-31"},
        )
        self.assertEqual(summary.status_code, 200)
        self.assertContains(summary, "Sara Flow")

        individual = self.client.get(
            reverse("report_individual_attendance"),
            {
                "employee": self.employee.pk,
                "date_from": "2026-03-01",
                "date_to": "2026-03-31",
            },
        )
        self.assertEqual(individual.status_code, 200)
        self.assertContains(individual, "Sara Flow")

    def test_csv_and_xlsx_exports_contain_the_data(self):
        self._punch_day()
        month = {"date_from": "2026-03-01", "date_to": "2026-03-31"}

        csv_response = self.client.get(
            reverse("report_attendance_summary"), {"format": "csv", **month}
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response["Content-Type"])
        self.assertIn("Sara Flow", csv_response.content.decode())

        xlsx_response = self.client.get(
            reverse("report_attendance_summary"), {"format": "xlsx", **month}
        )
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertIn(
            "spreadsheet", xlsx_response["Content-Type"]
        )
        self.assertTrue(len(xlsx_response.content) > 0)

        punch_csv = self.client.get(
            reverse("report_punch_log"), {"format": "csv", **month}
        )
        self.assertEqual(punch_csv.status_code, 200)
        self.assertIn("Sara Flow", punch_csv.content.decode())

    def test_employee_sees_own_attendance(self):
        row = self._punch_day()
        self.assertTrue(
            self.login_as(user=self.employee.user, via="email"),
            "employee login failed",
        )

        response = self.client.get(reverse("my_attendance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "March 9, 2026")
        self.assertContains(response, row.get_status_display())

        # ...but not the admin-wide punch table.
        admin_table = self.client.get(reverse("attendance_transaction_list"))
        self.assertEqual(admin_table.status_code, 403)
