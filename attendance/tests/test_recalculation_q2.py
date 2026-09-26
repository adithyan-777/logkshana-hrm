from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity
from attendance.q2_tasks import (
    calculate_employee_day,
    enqueue_tenant_day,
    fanout_daily_attendance,
)
from attendance.recalculation import recalculate_attendance
from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    employee_factory,
    schedule_factory,
    timetable_factory,
)
from employees.models import Employee
from schedule.models import EmployeeScheduleAssignment, EmployeeScheduleOverride


def aware_day(day, at):
    return timezone.make_aware(
        datetime.combine(day, at),
    )


class RecalculationTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.employee = employee_factory(first_name="Calc", emp_code="C001")
        self.timetable = timetable_factory(
            name="Office",
            code="OFF-CALC",
            check_in=time(9, 0),
            check_out=time(18, 0),
        )
        from schedule.services import timetable_break_create

        timetable_break_create(
            timetable=self.timetable,
            name="Lunch",
            start_time=time(13, 0),
            end_time=time(14, 0),
        )
        self.schedule = schedule_factory(name="Office Week", timetable=self.timetable)
        self.schedule.start_date = date(2026, 1, 1)
        self.schedule.save(update_fields=["start_date"])
        self.day = date(2026, 3, 9)

    def _assign(self):
        assignment = EmployeeScheduleAssignment.objects.create(
            schedule=self.schedule,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        assignment.employees.add(self.employee)
        return assignment

    def _punch(self, at, direction):
        return AttendanceActivity.objects.create(
            employee=self.employee,
            punch_time=aware_day(self.day, at),
            direction=direction,
            method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
        )

    def test_full_day_present_with_overtime(self):
        self._assign()
        self._punch(time(9, 0), "in")
        self._punch(time(18, 0), "out")

        row = recalculate_attendance(employee=self.employee, day=self.day)

        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.total_work_time, timedelta(minutes=540))
        self.assertEqual(row.over_time, timedelta(minutes=60))  # 540 - 480
        self.assertTrue(row.is_calculated)
        self.assertEqual(row.attendance_activities.count(), 2)
        self.assertEqual(row.shift, self.timetable)

    def test_late_arrival(self):
        self._assign()
        self._punch(time(9, 20), "in")
        self._punch(time(18, 0), "out")

        row = recalculate_attendance(employee=self.employee, day=self.day)

        self.assertEqual(row.status, Attendance.Status.LATE)
        self.assertEqual(row.total_work_time, timedelta(minutes=520))

    def test_lone_check_in_is_incomplete(self):
        self._assign()
        self._punch(time(9, 0), "in")

        row = recalculate_attendance(employee=self.employee, day=self.day)

        self.assertEqual(row.status, Attendance.Status.INCOMPLETE)

    def test_no_punches_with_assignment_is_absent(self):
        self._assign()

        row = recalculate_attendance(employee=self.employee, day=self.day)

        self.assertEqual(row.status, Attendance.Status.ABSENT)

    def test_no_punches_no_history_records_nothing(self):
        row = recalculate_attendance(employee=self.employee, day=self.day)

        self.assertIsNone(row)
        self.assertFalse(
            Attendance.objects.filter(employee=self.employee, day=self.day).exists()
        )

    def test_day_off_override_without_punches(self):
        self._assign()
        EmployeeScheduleOverride.objects.create(
            employee=self.employee, date=self.day, is_day_off=True
        )

        row = recalculate_attendance(employee=self.employee, day=self.day)

        self.assertEqual(row.status, Attendance.Status.DAY_OFF)

    def test_worked_day_off_is_present_with_full_overtime(self):
        self._assign()
        EmployeeScheduleOverride.objects.create(
            employee=self.employee, date=self.day, is_day_off=True
        )
        self._punch(time(9, 0), "in")
        self._punch(time(13, 0), "out")

        row = recalculate_attendance(employee=self.employee, day=self.day)

        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.over_time, timedelta(minutes=240))

    def test_manual_leave_row_is_preserved(self):
        self._assign()
        self._punch(time(9, 0), "in")
        self._punch(time(18, 0), "out")
        Attendance.objects.create(
            employee=self.employee,
            day=self.day,
            status=Attendance.Status.LEAVE,
            is_calculated=False,
        )

        row = recalculate_attendance(employee=self.employee, day=self.day)
        self.assertEqual(row.status, Attendance.Status.LEAVE)

        row = recalculate_attendance(employee=self.employee, day=self.day, force=True)
        self.assertEqual(row.status, Attendance.Status.PRESENT)


class CalculateEmployeeDayTaskTests(BaseTenantTestCase):
    def test_task_returns_json_safe_summary(self):
        employee = employee_factory(first_name="Task", emp_code="T001")
        timetable = timetable_factory(
            name="Office",
            code="OFF-TASK",
            check_in=time(9, 0),
            check_out=time(18, 0),
        )
        schedule = schedule_factory(name="Office Week", timetable=timetable)
        assignment = EmployeeScheduleAssignment.objects.create(
            schedule=schedule,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        assignment.employees.add(employee)
        day = date(2026, 3, 9)
        AttendanceActivity.objects.create(
            employee=employee,
            punch_time=aware_day(day, time(9, 0)),
            direction="in",
        )
        AttendanceActivity.objects.create(
            employee=employee,
            punch_time=aware_day(day, time(18, 0)),
            direction="out",
        )

        result = calculate_employee_day(
            self.tenant.schema_name, employee.id, day.isoformat()
        )

        self.assertTrue(result["recorded"])
        self.assertEqual(result["status"], Attendance.Status.PRESENT)
        self.assertEqual(result["day"], day.isoformat())


class EnqueueTests(BaseTenantTestCase):
    def test_enqueue_tenant_day_creates_one_task_per_employee(self):
        employee_factory(first_name="QOne", emp_code="Q001")
        employee_factory(first_name="QTwo", emp_code="Q002")
        day_iso = date(2026, 3, 9).isoformat()

        with patch("django_q.tasks.async_task") as mock_async:
            result = enqueue_tenant_day(self.tenant.schema_name, day_iso)

        active = Employee.objects.filter(is_active=True).count()
        self.assertEqual(result["employees"], active)
        self.assertEqual(mock_async.call_count, active)
        for call in mock_async.call_args_list:
            args, kwargs = call
            self.assertEqual(args[0], "attendance.q2_tasks.calculate_employee_day")
            self.assertEqual(args[1], self.tenant.schema_name)
            self.assertEqual(kwargs["group"], "attendance-calc")

    def test_fanout_enqueues_one_task_per_tenant(self):
        day_iso = date(2026, 3, 9).isoformat()
        with patch("django_q.tasks.async_task") as mock_async:
            result = fanout_daily_attendance(day_iso)

        self.assertGreaterEqual(result["tenants"], 1)
        self.assertEqual(mock_async.call_count, result["tenants"])
        for call in mock_async.call_args_list:
            args, kwargs = call
            self.assertEqual(args[0], "attendance.q2_tasks.enqueue_tenant_day")
            self.assertEqual(kwargs["group"], "attendance-calc")
