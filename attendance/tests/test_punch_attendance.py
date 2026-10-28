"""Tests for punch-driven Attendance row updates."""

from datetime import date, datetime, timedelta

from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity, WorkSession
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
        row = Attendance.objects.create(
            employee=employee,
            day=DAY,
            status=Attendance.Status.ABSENT,
            is_calculated=False,
        )

        returned = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8), direction="in"
        )

        self.assertEqual(returned, row)
        row.refresh_from_db()
        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.check_in, _dt(DAY, 8))
        self.assertIsNone(row.check_out)
        self.assertEqual(row.total_work_time, timedelta(0))
        session = WorkSession.objects.get(attendance=row)
        self.assertIsNone(session.check_out)
        self.assertEqual(session.total_time, timedelta(0))

    def test_in_creates_row_when_missing(self):
        employee = employee_factory(first_name="New", emp_code="PU002")

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8, 5), direction="in"
        )

        self.assertEqual(row.day, DAY)
        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.check_in, _dt(DAY, 8, 5))
        self.assertFalse(row.is_calculated)
        session = WorkSession.objects.get(attendance=row)
        self.assertEqual(session.check_in, _dt(DAY, 8, 5))

    def test_double_in_is_ignored_no_new_session(self):
        employee = employee_factory(first_name="Twice", emp_code="PU003")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8, 30), direction="in"
        )

        # First-in wins: no second session, boundaries unchanged.
        self.assertEqual(row.check_in, _dt(DAY, 8))
        self.assertEqual(
            WorkSession.objects.filter(employee=employee).count(), 1
        )

    def test_in_keeps_handmade_status(self):
        # A hand-made LEAVE row is not overwritten by a punch.
        employee = employee_factory(first_name="Leave", emp_code="PU004")
        row = Attendance.objects.create(
            employee=employee,
            day=DAY,
            status=Attendance.Status.LEAVE,
        )

        returned = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 9), direction="in"
        )

        self.assertEqual(returned, row)
        row.refresh_from_db()
        self.assertEqual(row.status, Attendance.Status.LEAVE)
        self.assertEqual(row.check_in, _dt(DAY, 9))
        self.assertTrue(
            WorkSession.objects.filter(attendance=row).exists()
        )


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
        session = WorkSession.objects.get(attendance=row)
        self.assertEqual(session.check_out, _dt(DAY, 17))
        self.assertEqual(session.total_time, timedelta(hours=9))

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

        # The OUT closes the open session from the IN's day, not today's.
        self.assertEqual(row.day, DAY)
        self.assertEqual(row.total_work_time, timedelta(hours=8))
        self.assertEqual(WorkSession.objects.first().day, DAY)
        self.assertFalse(Attendance.objects.filter(day=date(2026, 11, 3)).exists())

    def test_stray_out_creates_no_daily_row(self):
        employee = employee_factory(first_name="Stray", emp_code="PU007")

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 17), direction="out"
        )

        # No open session: the OUT stays punch-log-only and touches no row.
        self.assertIsNone(row)
        self.assertFalse(Attendance.objects.filter(employee=employee).exists())
        self.assertFalse(WorkSession.objects.filter(employee=employee).exists())

    def test_stale_out_never_pairs_backwards(self):
        employee = employee_factory(first_name="Stale", emp_code="PU013")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 9), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8), direction="out"
        )

        self.assertIsNone(row)
        session = WorkSession.objects.get(employee=employee)
        self.assertIsNone(session.check_out)
        stored = Attendance.objects.get(employee=employee, day=DAY)
        self.assertIsNone(stored.check_out)
        self.assertEqual(stored.total_work_time, timedelta(0))


class SplitDayTests(BaseTenantTestCase):
    """Multiple in/out pairs in one day sum into total_work_time."""

    def test_two_sessions_sum_their_durations(self):
        employee = employee_factory(first_name="Split", emp_code="PU014")

        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 9), direction="in"
        )
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 14), direction="out"
        )
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 15), direction="in"
        )
        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 20), direction="out"
        )

        self.assertEqual(row.check_in, _dt(DAY, 9))
        self.assertEqual(row.check_out, _dt(DAY, 20))
        self.assertEqual(row.total_work_time, timedelta(hours=10))
        sessions = WorkSession.objects.filter(attendance=row).order_by("check_in")
        self.assertEqual(sessions.count(), 2)
        first, second = list(sessions)
        self.assertEqual(first.total_time, timedelta(hours=5))
        self.assertEqual(second.total_time, timedelta(hours=5))
        self.assertEqual(second.check_out, _dt(DAY, 20))

    def test_new_session_opens_after_close(self):
        employee = employee_factory(first_name="Again", emp_code="PU015")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 9), direction="in"
        )
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 14), direction="out"
        )

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 15), direction="in"
        )

        self.assertEqual(row.check_out, _dt(DAY, 14))
        self.assertTrue(
            WorkSession.objects.filter(employee=employee, check_out=None).exists()
        )


class PunchConsumptionLinkTests(BaseTenantTestCase):
    def test_punches_link_to_day_row(self):
        _unschedule_tenant()
        employee = employee_factory(first_name="Link", emp_code="PU016")
        in_punch = activity_create(
            employee=employee, punch_time=_dt(DAY, 8), direction="in"
        )
        out_punch = activity_create(
            employee=employee, punch_time=_dt(DAY, 17), direction="out"
        )
        row = Attendance.objects.get(employee=employee, day=DAY)

        in_punch.refresh_from_db()
        out_punch.refresh_from_db()
        self.assertTrue(in_punch.is_attendance_processed)
        self.assertTrue(out_punch.is_attendance_processed)
        self.assertEqual(in_punch.attendance, row)
        self.assertEqual(out_punch.attendance, row)
        session = WorkSession.objects.get(attendance=row)
        self.assertEqual(session.in_punch, in_punch)
        self.assertEqual(session.out_punch, out_punch)


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
        session = WorkSession.objects.get(attendance=row)
        self.assertEqual(session.total_time, timedelta(hours=9))
