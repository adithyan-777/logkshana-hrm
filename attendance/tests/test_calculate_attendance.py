"""Tests for attendance.recalculation.calculate_attendance.

Covers the grouped comparison: scheduled employees with no activity
punch are absentees; punched employees past expected check-in are
late arrivals.
"""

import io
from contextlib import redirect_stdout
from datetime import date, datetime

from django.utils import timezone

from attendance.models import Attendance
from attendance.recalculation import calculate_attendance
from attendance.services import activity_create
from common.tests.base import BaseTenantTestCase
from common.tests.factories import employee_factory, schedule_factory
from schedule.models import EmployeeScheduleAssignment


def _assign(*, schedule, employees, start, end):
    assignment = EmployeeScheduleAssignment.objects.create(
        schedule=schedule,
        start_date=start,
        end_date=end,
    )
    assignment.employees.add(*employees)
    return assignment


def _punch(*, employee, day, hour, minute=0):
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
        recalculate=False,
    )


class CalculateAttendanceGroupsTests(BaseTenantTestCase):
    def test_absentees_and_late_arrivals_grouped(self):
        day = date(2026, 9, 24)
        on_time = employee_factory(first_name="Ontime", emp_code="GRP001")
        late = employee_factory(first_name="Late", emp_code="GRP002")
        absent = employee_factory(first_name="Absent", emp_code="GRP003")
        schedule = schedule_factory(name="Group Sched")  # 09:00-18:00

        _assign(
            schedule=schedule,
            employees=[on_time, late, absent],
            start=date(2026, 9, 1),
            end=date(2026, 9, 30),
        )

        _punch(employee=on_time, day=day, hour=9, minute=0)
        _punch(employee=on_time, day=day, hour=17, minute=0)
        _punch(employee=late, day=day, hour=9, minute=30)

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = calculate_attendance(day=day)
        printed = buf.getvalue().strip()

        print(f"calculate_attendance printed: {printed!r}")

        self.assertEqual(result["absentees"], [absent])
        self.assertEqual(
            [employee for employee, _ in result["late_arrivals"]], [late]
        )
        self.assertEqual(
            [
                (employee, minutes)
                for employee, minutes, _, _ in result["work_hours"]
            ],
            [(on_time, 480)],
        )
        self.assertIn("Late arrivals:", printed)
        self.assertIn("Work hours:", printed)
        self.assertIn("Created attendance:", printed)
        self.assertIn("Absent", printed)
        self.assertIn("Late", printed)
        self.assertIn("Ontime Doe: 8h 00m", printed)

        # Every scheduled employee gets an Attendance row:
        # complete pairs -> PRESENT/LATE/EARLY_OUT, single punch ->
        # INCOMPLETE, no punches -> ABSENT.
        created = result["created"]
        self.assertEqual(len(created), 3)
        by_employee = {row.employee_id: row for row in created}
        self.assertEqual(by_employee[on_time.pk].day, day)
        self.assertTrue(
            Attendance.objects.filter(employee=on_time, day=day).exists()
        )
        late_row = Attendance.objects.get(employee=late, day=day)
        self.assertEqual(late_row.status, Attendance.Status.INCOMPLETE)
        absent_row = Attendance.objects.get(employee=absent, day=day)
        self.assertEqual(absent_row.status, Attendance.Status.ABSENT)
        self.assertEqual(result["incomplete"], [late])

    def test_empty_groups_when_everyone_on_time(self):
        day = date(2026, 9, 24)
        employee = employee_factory(first_name="Only", emp_code="GRP004")
        schedule = schedule_factory(name="Full Sched")

        _assign(
            schedule=schedule,
            employees=[employee],
            start=date(2026, 9, 1),
            end=date(2026, 9, 30),
        )

        _punch(employee=employee, day=day, hour=9, minute=0)

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = calculate_attendance(day=day)

        self.assertEqual(
            {
                k: v
                for k, v in result.items()
                if k not in ("created", "incomplete")
            },
            {"absentees": [], "late_arrivals": [], "work_hours": []},
        )
        # Single punch -> INCOMPLETE row is still created.
        self.assertEqual(result["incomplete"], [employee])
        self.assertEqual(len(result["created"]), 1)
        self.assertEqual(
            result["created"][0].status, Attendance.Status.INCOMPLETE
        )
        self.assertIn("Late arrivals:", buf.getvalue())
        self.assertIn("Work hours:", buf.getvalue())
        self.assertIn("Created attendance:", buf.getvalue())
