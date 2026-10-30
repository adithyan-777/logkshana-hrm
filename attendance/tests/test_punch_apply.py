"""Tests for manual-punch / correction re-coupling (punch_apply).

Editing or deleting a punch must rebuild the WorkSession and daily
Attendance rows that the punch derived — the pairing primitive can
only pair forward, it never un-pairs.
"""

from datetime import date, datetime, timedelta

from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity, WorkSession
from attendance.services import (
    activity_create,
    punch_delete,
    punch_edit,
)
from common.tests.base import BaseTenantTestCase
from common.tests.factories import employee_factory
from policies.models import AttendancePolicy

DAY = date(2026, 11, 2)
NEXT_DAY = date(2026, 11, 3)
DAY3 = date(2026, 11, 4)
DAY4 = date(2026, 11, 5)

METHOD = AttendanceActivity.AttendanceActivityMethodType.MANUAL


def _dt(day, hour, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute,
                    tzinfo=timezone.get_current_timezone())


def _unschedule_tenant():
    """Flip the tenant policy to unscheduled (punch calculation on)."""
    AttendancePolicy.objects.create(
        schedule_mode=AttendancePolicy.ScheduleMode.UNSCHEDULED
    )


def _punch(employee, direction, day, hour, minute=0):
    return activity_create(
        employee=employee,
        punch_time=_dt(day, hour, minute),
        direction=direction,
        method=METHOD,
    )


class PunchEditTests(BaseTenantTestCase):
    def setUp(self):
        self.employee = employee_factory(first_name="Edit", emp_code="PA001")
        _unschedule_tenant()

    def test_edit_moves_session_and_row_boundaries(self):
        activity = _punch(self.employee, "in", DAY, 8)

        rows = punch_edit(
            activity=activity,
            employee=self.employee,
            punch_time=_dt(DAY, 9),
            direction="in",
            method=METHOD,
        )

        row = rows[0]
        self.assertEqual(row.day, DAY)
        row.refresh_from_db()
        self.assertEqual(row.check_in, _dt(DAY, 9))
        self.assertEqual(row.status, Attendance.Status.PRESENT)
        session = WorkSession.objects.get(employee=self.employee)
        self.assertEqual(session.check_in, _dt(DAY, 9))
        self.assertIsNone(session.check_out)

    def test_edit_direction_in_to_out_leaves_stray_out(self):
        # The punch was an IN (row PRESENT with an open session);
        # corrected to an OUT it pairs with nothing: the session is
        # rebuilt away and the row demotes to INCOMPLETE.
        activity = _punch(self.employee, "in", DAY, 8)

        rows = punch_edit(
            activity=activity,
            employee=self.employee,
            punch_time=_dt(DAY, 18),
            direction="out",
            method=METHOD,
        )

        row = rows[0]
        row.refresh_from_db()
        self.assertEqual(row.status, Attendance.Status.INCOMPLETE)
        self.assertIsNone(row.check_in)
        self.assertIsNone(row.check_out)
        self.assertEqual(row.total_work_time, timedelta(0))
        self.assertFalse(
            WorkSession.objects.filter(employee=self.employee).exists()
        )

    def test_edit_overnight_out_time_moves_total(self):
        # 22:00 IN, 03:00 OUT (next day, 5h). Correct the OUT to 04:00:
        # the session and the IN day's row grow to 6h; the OUT day gets
        # no row.
        _punch(self.employee, "in", DAY, 22)
        activity_out = _punch(self.employee, "out", NEXT_DAY, 3)

        rows = punch_edit(
            activity=activity_out,
            employee=self.employee,
            punch_time=_dt(NEXT_DAY, 4),
            direction="out",
            method=METHOD,
        )

        row = rows[0]
        self.assertEqual(row.day, DAY)
        row.refresh_from_db()
        self.assertEqual(row.check_in, _dt(DAY, 22))
        self.assertEqual(row.check_out, _dt(NEXT_DAY, 4))
        self.assertEqual(row.total_work_time, timedelta(hours=6))
        session = WorkSession.objects.get(employee=self.employee)
        self.assertEqual(session.total_time, timedelta(hours=6))
        self.assertFalse(
            Attendance.objects.filter(employee=self.employee, day=NEXT_DAY)
            .exists()
        )

    def test_edit_moves_punch_across_days(self):
        activity = _punch(self.employee, "in", DAY, 9)

        rows = punch_edit(
            activity=activity,
            employee=self.employee,
            punch_time=_dt(NEXT_DAY, 9),
            direction="in",
            method=METHOD,
        )

        by_day = {row.day: row for row in rows}
        old = by_day[DAY]
        old.refresh_from_db()
        self.assertEqual(old.status, Attendance.Status.INCOMPLETE)
        self.assertIsNone(old.check_in)
        self.assertEqual(old.total_work_time, timedelta(0))
        new = by_day[NEXT_DAY]
        self.assertEqual(new.status, Attendance.Status.PRESENT)
        self.assertEqual(new.check_in, _dt(NEXT_DAY, 9))
        self.assertEqual(
            WorkSession.objects.get(employee=self.employee).day, NEXT_DAY
        )

    def test_edit_moves_punch_between_employees(self):
        other = employee_factory(first_name="Other", emp_code="PA002")
        activity = _punch(self.employee, "in", DAY, 9)

        punch_edit(
            activity=activity,
            employee=other,
            punch_time=_dt(DAY, 9),
            direction="in",
            method=METHOD,
        )

        old_row = Attendance.objects.get(employee=self.employee, day=DAY)
        self.assertEqual(old_row.status, Attendance.Status.INCOMPLETE)
        self.assertFalse(
            WorkSession.objects.filter(employee=self.employee).exists()
        )
        new_row = Attendance.objects.get(employee=other, day=DAY)
        self.assertEqual(new_row.status, Attendance.Status.PRESENT)
        self.assertEqual(new_row.check_in, _dt(DAY, 9))

    def test_edit_keeps_handmade_status(self):
        # A hand-made LEAVE row is not overwritten by a punch
        # correction (only ABSENT/INCOMPLETE flip to PRESENT).
        row = Attendance.objects.create(
            employee=self.employee,
            day=DAY,
            status=Attendance.Status.LEAVE,
        )
        activity = _punch(self.employee, "in", DAY, 9)

        rows = punch_edit(
            activity=activity,
            employee=self.employee,
            punch_time=_dt(DAY, 10),
            direction="in",
            method=METHOD,
        )

        self.assertEqual(rows[0], row)
        row.refresh_from_db()
        self.assertEqual(row.status, Attendance.Status.LEAVE)
        self.assertEqual(row.check_in, _dt(DAY, 10))

    def test_edit_shrinks_multi_day_window_to_out_of_window_out(self):
        # Mon 22:00 IN; Tue 08:00 IN; (no opening time → unbounded) a
        # Thursday 05:00 OUT closes Tuesday's session. Editing Monday's
        # IN must not lose Thursday's close even though it is outside
        # the natural Mon±1 window.
        _punch(self.employee, "in", DAY, 22)
        _punch(self.employee, "in", NEXT_DAY, 8)
        _punch(self.employee, "out", DAY4, 5)
        activity_mon = AttendanceActivity.objects.get(
            employee=self.employee, direction="in", punch_time=_dt(DAY, 22)
        )

        punch_edit(
            activity=activity_mon,
            employee=self.employee,
            punch_time=_dt(DAY, 21),
            direction="in",
            method=METHOD,
        )

        monday_session = WorkSession.objects.get(
            employee=self.employee, day=DAY
        )
        self.assertEqual(monday_session.check_in, _dt(DAY, 21))
        self.assertIsNone(monday_session.check_out)
        tuesday_session = WorkSession.objects.get(
            employee=self.employee, day=NEXT_DAY
        )
        self.assertEqual(tuesday_session.check_out, _dt(DAY4, 5))
        self.assertEqual(tuesday_session.total_time, timedelta(hours=45))


class PunchDeleteTests(BaseTenantTestCase):
    def setUp(self):
        self.employee = employee_factory(first_name="Del", emp_code="PD001")
        _unschedule_tenant()

    def test_delete_out_reopens_overnight_session(self):
        _punch(self.employee, "in", DAY, 22)
        activity_out = _punch(self.employee, "out", NEXT_DAY, 3)

        rows = punch_delete(activity=activity_out)

        row = rows[0]
        self.assertEqual(row.day, DAY)
        row.refresh_from_db()
        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.check_in, _dt(DAY, 22))
        self.assertIsNone(row.check_out)
        self.assertEqual(row.total_work_time, timedelta(0))
        session = WorkSession.objects.get(employee=self.employee)
        self.assertIsNone(session.check_out)
        self.assertEqual(session.total_time, timedelta(0))

    def test_delete_in_removes_session_and_demotes_row(self):
        activity = _punch(self.employee, "in", DAY, 9)

        rows = punch_delete(activity=activity)

        row = rows[0]
        row.refresh_from_db()
        self.assertEqual(row.status, Attendance.Status.INCOMPLETE)
        self.assertIsNone(row.check_in)
        self.assertEqual(row.total_work_time, timedelta(0))
        self.assertFalse(
            WorkSession.objects.filter(employee=self.employee).exists()
        )

    def test_delete_only_touches_its_own_session(self):
        # Double punch: OUT 17:00 closes the 09:00 session. Deleting
        # the 08:00 punch takes its session alone and keeps the closed
        # 09:00 → 17:00 one.
        _punch(self.employee, "in", DAY, 8)
        _punch(self.employee, "in", DAY, 9)
        _punch(self.employee, "out", DAY, 17)
        activity_early = AttendanceActivity.objects.get(
            employee=self.employee, direction="in", punch_time=_dt(DAY, 8)
        )

        punch_delete(activity=activity_early)

        sessions = WorkSession.objects.filter(
            employee=self.employee
        ).order_by("check_in")
        self.assertEqual(sessions.count(), 1)
        kept = sessions.get()
        self.assertEqual(kept.check_in, _dt(DAY, 9))
        self.assertEqual(kept.check_out, _dt(DAY, 17))
        self.assertEqual(kept.total_time, timedelta(hours=8))
        row = Attendance.objects.get(employee=self.employee, day=DAY)
        self.assertEqual(row.check_in, _dt(DAY, 9))
        self.assertEqual(row.check_out, _dt(DAY, 17))
        self.assertEqual(row.total_work_time, timedelta(hours=8))

    def test_delete_keeps_handmade_leave_row(self):
        Attendance.objects.create(
            employee=self.employee,
            day=DAY,
            status=Attendance.Status.LEAVE,
        )
        activity = _punch(self.employee, "in", DAY, 9, 30)

        punch_delete(activity=activity)

        row = Attendance.objects.get(employee=self.employee, day=DAY)
        self.assertEqual(row.status, Attendance.Status.LEAVE)
        self.assertIsNone(row.check_in)
        self.assertEqual(row.total_work_time, timedelta(0))

    def test_deleted_punch_row_disappears_from_punch_log(self):
        activity = _punch(self.employee, "out", DAY, 17)

        punch_delete(activity=activity)

        self.assertFalse(
            AttendanceActivity.objects.filter(pk=activity.pk).exists()
        )
