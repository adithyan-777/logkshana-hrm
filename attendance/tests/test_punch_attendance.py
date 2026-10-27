"""Tests for punch-driven Attendance row updates."""

from datetime import date, datetime, timedelta

from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity
from attendance.services import activity_create, attendance_update_for_punch
from common.tests.base import BaseTenantTestCase
from common.tests.factories import device_factory, employee_factory
from companies.services import attendance_log_create
from policies.models import AttendancePolicy

DAY = date(2026, 11, 2)


def _dt(day, hour, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute,
                    tzinfo=timezone.get_current_timezone())


def _unschedule_tenant():
    """Flip the tenant policy to unscheduled (punch calculation on)."""
    AttendancePolicy.objects.create(
        schedule_mode=AttendancePolicy.ScheduleMode.UNSCHEDULED
    )


class PunchInTests(BaseTenantTestCase):
    def test_in_flips_precreated_absent_row_to_present(self):
        employee = employee_factory(first_name="Pre", emp_code="PU001")
        Attendance.objects.create(
            employee=employee,
            day=DAY,
            status=Attendance.Status.ABSENT,
            is_calculated=False,
        )

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8), direction="in"
        )

        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.check_in, _dt(DAY, 8))
        self.assertIsNone(row.check_out)
        self.assertEqual(row.total_work_time, timedelta(0))

    def test_in_creates_row_when_missing(self):
        employee = employee_factory(first_name="New", emp_code="PU002")

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8, 5), direction="in"
        )

        self.assertEqual(row.day, DAY)
        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.check_in, _dt(DAY, 8, 5))
        self.assertFalse(row.is_calculated)

    def test_double_in_first_in_wins(self):
        employee = employee_factory(first_name="Twice", emp_code="PU003")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8, 30), direction="in"
        )

        self.assertEqual(row.check_in, _dt(DAY, 8))

    def test_in_keeps_handmade_status(self):
        # A hand-made LEAVE row is not overwritten by a punch.
        employee = employee_factory(first_name="Leave", emp_code="PU004")
        Attendance.objects.create(
            employee=employee,
            day=DAY,
            status=Attendance.Status.LEAVE,
        )

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 9), direction="in"
        )

        self.assertEqual(row.status, Attendance.Status.LEAVE)
        self.assertEqual(row.check_in, _dt(DAY, 9))


class PunchOutTests(BaseTenantTestCase):
    def test_out_same_day_computes_work_time(self):
        employee = employee_factory(first_name="Work", emp_code="PU005")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 17), direction="out"
        )

        self.assertEqual(row.day, DAY)
        self.assertEqual(row.check_out, _dt(DAY, 17))
        self.assertEqual(row.total_work_time, timedelta(hours=9))
        self.assertEqual(row.status, Attendance.Status.PRESENT)

    def test_out_overnight_closes_yesterdays_row(self):
        employee = employee_factory(first_name="Night", emp_code="PU006")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 22), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee,
            punch_time=_dt(date(2026, 11, 3), 6),
            direction="out",
        )

        # The OUT closes the open row from the IN's day, not today's.
        self.assertEqual(row.day, DAY)
        self.assertEqual(row.total_work_time, timedelta(hours=8))
        self.assertFalse(Attendance.objects.filter(day=date(2026, 11, 3)).exists())

    def test_out_without_open_row_records_on_todays_row(self):
        employee = employee_factory(first_name="Stray", emp_code="PU007")

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 17), direction="out"
        )

        self.assertEqual(row.day, DAY)
        self.assertEqual(row.check_out, _dt(DAY, 17))
        self.assertIsNone(row.check_in)
        self.assertEqual(row.total_work_time, timedelta(0))
        self.assertEqual(row.status, Attendance.Status.INCOMPLETE)

    def test_out_closes_most_recent_open_row(self):
        # Two open rows (incomplete check-out yesterday) — the OUT
        # closes the latest one.
        employee = employee_factory(first_name="Two", emp_code="PU008")
        Attendance.objects.create(
            employee=employee,
            day=date(2026, 11, 1),
            check_in=_dt(date(2026, 11, 1), 8),
        )
        Attendance.objects.create(
            employee=employee, day=DAY, check_in=_dt(DAY, 8)
        )

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 17), direction="out"
        )

        self.assertEqual(row.day, DAY)
        self.assertEqual(row.total_work_time, timedelta(hours=9))
        older = Attendance.objects.get(employee=employee, day=date(2026, 11, 1))
        self.assertIsNone(older.check_out)


class UnknownDirectionTests(BaseTenantTestCase):
    def test_unknown_direction_leaves_rows_alone(self):
        _unschedule_tenant()
        employee = employee_factory(first_name="Unk", emp_code="PU009")
        activity_create(
            employee=employee,
            punch_time=_dt(DAY, 8),
            direction=AttendanceActivity.Direction.UNKNOWN,
        )

        self.assertFalse(Attendance.objects.filter(employee=employee).exists())


class PunchPolicyGatingTests(BaseTenantTestCase):
    """Punch calculation only runs when the tenant policy is unscheduled."""

    def test_scheduled_mode_records_punch_without_attendance_row(self):
        employee = employee_factory(first_name="Sched", emp_code="PU010")

        activity_create(
            employee=employee,
            punch_time=_dt(DAY, 8),
            direction=AttendanceActivity.Direction.IN,
        )

        self.assertTrue(
            AttendanceActivity.objects.filter(employee=employee).exists()
        )
        self.assertFalse(Attendance.objects.filter(employee=employee).exists())

    def test_unscheduled_mode_updates_attendance_row(self):
        _unschedule_tenant()
        employee = employee_factory(first_name="Unsch", emp_code="PU011")

        activity_create(
            employee=employee,
            punch_time=_dt(DAY, 8),
            direction=AttendanceActivity.Direction.IN,
        )

        row = Attendance.objects.get(employee=employee, day=DAY)
        self.assertEqual(row.check_in, _dt(DAY, 8))
        self.assertEqual(row.status, Attendance.Status.PRESENT)

    def test_direct_call_ignores_policy(self):
        # attendance_update_for_punch is the calculation primitive:
        # callers (gateway push views) may invoke it regardless of mode.
        employee = employee_factory(first_name="Direct", emp_code="PU012")

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8), direction="in"
        )

        self.assertEqual(row.check_in, _dt(DAY, 8))


class GatewayEndToEndTests(BaseTenantTestCase):
    def test_gateway_push_updates_attendance_row(self):
        _unschedule_tenant()
        device_factory(serial_number="PU-GW1", company=self.tenant)
        employee = employee_factory(first_name="Gw", emp_code="1001")

        attendance_log_create(
            serial_number="PU-GW1",
            employee_id="1001",
            timestamp=_dt(DAY, 8),
            extra_raw_data={"status_label": "Check In"},
        )
        row = Attendance.objects.get(employee=employee, day=DAY)
        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.check_in, _dt(DAY, 8))

        attendance_log_create(
            serial_number="PU-GW1",
            employee_id="1001",
            timestamp=_dt(DAY, 17),
            extra_raw_data={"status_label": "Check Out"},
        )
        row.refresh_from_db()
        self.assertEqual(row.check_out, _dt(DAY, 17))
        self.assertEqual(row.total_work_time, timedelta(hours=9))
