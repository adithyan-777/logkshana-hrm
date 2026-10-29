"""Tests for punch-driven Attendance row updates."""

from datetime import date, datetime, time, timedelta

from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity, WorkSession
from attendance.services import activity_create, attendance_update_for_punch
from common.tests.base import BaseTenantTestCase
from common.tests.factories import device_factory, employee_factory
from companies.services import attendance_log_create
from policies.models import AttendancePolicy, UnscheduledConfig

DAY = date(2026, 11, 2)
NEXT_DAY = date(2026, 11, 3)


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

    def test_double_in_opens_new_session(self):
        employee = employee_factory(first_name="Twice", emp_code="PU003")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8, 30), direction="in"
        )

        # Every IN opens its own session; the earlier one stays open
        # (its OUT never came) and the day's first check_in is kept.
        self.assertEqual(row.check_in, _dt(DAY, 8))
        sessions = WorkSession.objects.filter(
            employee=employee
        ).order_by("check_in")
        self.assertEqual(sessions.count(), 2)
        first, second = list(sessions)
        self.assertIsNone(first.check_out)
        self.assertEqual(first.check_in, _dt(DAY, 8))
        self.assertIsNone(second.check_out)
        self.assertEqual(second.check_in, _dt(DAY, 8, 30))

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
            punch_time=_dt(date(2026, 11, 3), 3),
            direction="out",
        )

        # The OUT closes the open session from the IN's day, not today's.
        self.assertEqual(row.day, DAY)
        self.assertEqual(row.total_work_time, timedelta(hours=5))
        self.assertEqual(WorkSession.objects.first().day, DAY)
        self.assertFalse(Attendance.objects.filter(day=date(2026, 11, 3)).exists())


class ForgottenPunchOutTests(BaseTenantTestCase):
    """Next-day punches when yesterday's session was never closed.

    The likely story is a forgotten check-out: an IN on the new day
    must open a fresh session (not be absorbed), while an OUT belongs
    to yesterday only earlier than the tenant's configured opening
    time (UnscheduledConfig.opening_time); with no configured opening
    the boundary is unbounded and any next-day OUT closes yesterday's
    session.
    """

    @staticmethod
    def _tenant_opening(opening_time: time):
        """Configure the tenant's day boundary (next-day-OUT cutoff)."""
        UnscheduledConfig.objects.create(opening_time=opening_time)

    def test_in_next_day_opens_new_session(self):
        employee = employee_factory(first_name="Forgot", emp_code="PU017")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 22), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(NEXT_DAY, 6), direction="in"
        )

        self.assertEqual(row.day, NEXT_DAY)
        self.assertEqual(row.check_in, _dt(NEXT_DAY, 6))
        self.assertEqual(row.status, Attendance.Status.PRESENT)
        sessions = WorkSession.objects.filter(
            employee=employee
        ).order_by("check_in")
        self.assertEqual(sessions.count(), 2)
        stale, fresh = list(sessions)
        # Yesterday's session stays open (its check-out genuinely never
        # happened); the new-day session does not steal its punches.
        self.assertIsNone(stale.check_out)
        self.assertEqual(stale.day, DAY)
        self.assertEqual(fresh.day, NEXT_DAY)
        self.assertIsNone(fresh.check_out)
        # The new-day row is fresh: no punches were stolen from yesterday.
        self.assertIsNone(
            Attendance.objects.get(employee=employee, day=DAY).check_out
        )

    def test_out_next_day_before_configured_opening_closes_yesterday(self):
        self._tenant_opening(time(4, 0))
        employee = employee_factory(first_name="Night", emp_code="PU018")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 22), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee,
            punch_time=_dt(NEXT_DAY, 3),
            direction="out",
        )

        # 03:00 is before the configured opening (04:00): overnight wrap.
        self.assertEqual(row.day, DAY)
        self.assertEqual(row.total_work_time, timedelta(hours=5))
        session = WorkSession.objects.get(employee=employee)
        self.assertEqual(session.check_out, _dt(NEXT_DAY, 3))
        self.assertFalse(Attendance.objects.filter(day=NEXT_DAY).exists())

    def test_out_next_day_at_configured_opening_closes_yesterday(self):
        self._tenant_opening(time(4, 0))
        employee = employee_factory(first_name="Edge", emp_code="PU023")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 22), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee,
            punch_time=_dt(NEXT_DAY, 4),
            direction="out",
        )

        # Strict comparison: exactly at the opening still counts as the
        # overnight wrap. The boundary crossing is `> opening`.
        self.assertEqual(row.day, DAY)
        self.assertEqual(row.total_work_time, timedelta(hours=6))
        session = WorkSession.objects.get(employee=employee)
        self.assertEqual(session.check_out, _dt(NEXT_DAY, 4))

    def test_out_next_day_after_configured_opening_is_stray(self):
        self._tenant_opening(time(4, 0))
        employee = employee_factory(first_name="Forgot", emp_code="PU019")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 22), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee,
            punch_time=_dt(NEXT_DAY, 6),
            direction="out",
        )

        # 06:00 is past the configured opening (04:00): yesterday's
        # session was never closed and this OUT is the new day's stray.
        self.assertIsNone(row)
        session = WorkSession.objects.get(employee=employee)
        self.assertIsNone(session.check_out)
        self.assertEqual(session.total_time, timedelta(0))
        stored = Attendance.objects.get(employee=employee, day=DAY)
        self.assertIsNone(stored.check_out)
        self.assertEqual(stored.total_work_time, timedelta(0))

    def test_out_next_day_with_no_config_is_unbounded(self):
        # No UnscheduledConfig row (or null opening_time): no day
        # boundary — any next-day OUT closes yesterday's session.
        employee = employee_factory(first_name="Boundless", emp_code="PU024")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 22), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee,
            punch_time=_dt(NEXT_DAY, 6),
            direction="out",
        )

        self.assertEqual(row.day, DAY)
        self.assertEqual(row.total_work_time, timedelta(hours=8))
        session = WorkSession.objects.get(employee=employee)
        self.assertEqual(session.check_out, _dt(NEXT_DAY, 6))

    def test_null_opening_time_is_unbounded_too(self):
        self._tenant_opening(None)
        employee = employee_factory(first_name="NullBound", emp_code="PU025")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 22), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee,
            punch_time=_dt(NEXT_DAY, 6),
            direction="out",
        )

        self.assertEqual(row.day, DAY)
        self.assertEqual(row.total_work_time, timedelta(hours=8))

    def test_next_day_stray_out_keeps_session_open_in_scheduled_mode_too(
        self,
    ):
        # The day boundary is policy-independent: the pairing primitive
        # is called directly (gateway path) in any mode — only the
        # configured opening decides, not the attendance policy mode.
        self._tenant_opening(time(4, 0))
        employee = employee_factory(first_name="Direct", emp_code="PU020")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 22), direction="in"
        )

        row = attendance_update_for_punch(
            employee=employee,
            punch_time=_dt(NEXT_DAY, 6),
            direction="out",
        )

        self.assertIsNone(row)


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


class ReplayIdempotencyTests(BaseTenantTestCase):
    """Replaying a punch stream must be a no-op, not a second pairing.

    Recalculation scripts (and gateway replays) re-feed punches whose
    work already exists; the primitive must return the original state
    instead of tripping uniq_worksession_in_punch or re-closing
    another open session.
    """

    def test_replaying_in_and_out_leaves_one_closed_session(self):
        _unschedule_tenant()
        employee = employee_factory(first_name="Replay", emp_code="PU021")
        in_a = activity_create(employee=employee, punch_time=_dt(DAY, 8), direction="in")
        out_a = activity_create(employee=employee, punch_time=_dt(DAY, 17), direction="out")

        for _ in range(2):
            attendance_update_for_punch(
                employee=employee, punch_time=in_a.punch_time,
                direction="in", activity=in_a,
            )
            attendance_update_for_punch(
                employee=employee, punch_time=out_a.punch_time,
                direction="out", activity=out_a,
            )

        self.assertEqual(WorkSession.objects.filter(employee=employee).count(), 1)
        session = WorkSession.objects.get(employee=employee)
        self.assertEqual(session.check_out, _dt(DAY, 17))
        self.assertEqual(session.total_time, timedelta(hours=9))
        row = Attendance.objects.get(employee=employee, day=DAY)
        self.assertEqual(row.total_work_time, timedelta(hours=9))

    def test_out_without_activity_replay_guard_sits_out(self):
        # Direct-tool calls (activity=None) bypass the replay guard on
        # purpose — the punch log linkage is what makes a call replay.
        employee = employee_factory(first_name="Direct", emp_code="PU022")
        attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 8), direction="in"
        )
        row = attendance_update_for_punch(
            employee=employee, punch_time=_dt(DAY, 17), direction="out"
        )
        self.assertEqual(row.check_out, _dt(DAY, 17))


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
