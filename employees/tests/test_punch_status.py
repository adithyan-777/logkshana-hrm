from datetime import UTC, datetime, timedelta

from django.utils import timezone

from attendance.models import AttendanceActivity
from attendance.services import activity_create, activity_delete, activity_update
from common.tests.base import BaseTenantTestCase
from common.tests.factories import activity_factory, employee_factory
from employees.services import employee_punch_status_recompute


class EmployeePunchStatusDisplayTests(BaseTenantTestCase):
    """The badge time must read tenant-local (like the punch log), UTC."""

    def test_display_time_converts_utc_storage_to_local(self):
        from django.utils import timezone as dj_timezone

        employee = employee_factory(first_name="Tz", emp_code="PS300")
        # 2030-01-01 22:15 UTC == 2030-01-02 01:15 in Asia/Qatar (+03:00):
        # a raw UTC strftime would print "22:15" — the bug being guarded.
        punch_time = datetime(2030, 1, 1, 22, 15, tzinfo=UTC)
        activity_create(
            employee=employee,
            punch_time=punch_time,
            direction=AttendanceActivity.Direction.IN,
        )
        employee.refresh_from_db()

        expected = dj_timezone.localtime(employee.punch_time).strftime("%H:%M")
        self.assertEqual(expected, "01:15")
        self.assertEqual(employee.punch_display_time, expected)

    def test_display_time_empty_without_punch(self):
        employee = employee_factory(first_name="NoTz", emp_code="PS301")

        self.assertEqual(employee.punch_display_time, "")


class EmployeePunchStatusRecomputeTests(BaseTenantTestCase):
    """The mirror service itself: latest-punch derivation per direction."""

    def test_no_punches_means_blank(self):
        employee = employee_factory(first_name="Fresh", emp_code="PS100")

        employee = employee_punch_status_recompute(employee=employee)

        self.assertEqual(employee.punch_status, "")
        self.assertIsNone(employee.punch_time)

    def test_latest_direction_is_mirrored_for_every_direction(self):
        directions = [
            (AttendanceActivity.Direction.IN, AttendanceActivity.Direction.IN),
            (AttendanceActivity.Direction.OUT, AttendanceActivity.Direction.OUT),
            (
                AttendanceActivity.Direction.BREAK_IN,
                AttendanceActivity.Direction.BREAK_IN,
            ),
            (
                AttendanceActivity.Direction.BREAK_OUT,
                AttendanceActivity.Direction.BREAK_OUT,
            ),
            (
                AttendanceActivity.Direction.OVERTIME_IN,
                AttendanceActivity.Direction.OVERTIME_IN,
            ),
            (
                AttendanceActivity.Direction.OVERTIME_OUT,
                AttendanceActivity.Direction.OVERTIME_OUT,
            ),
        ]
        employee = employee_factory(first_name="Spec", emp_code="PS101")
        base = timezone.now()

        for punch_direction, expected in directions:
            activity_factory(
                employee=employee,
                punch_time=base,
                direction=punch_direction,
                method=AttendanceActivity.AttendanceActivityMethodType.MANUAL,
            )
            employee.refresh_from_db()
            self.assertEqual(employee.punch_status, expected)

    def test_unknown_punch_is_not_mirrored(self):
        employee = employee_factory(first_name="Mute", emp_code="PS102")

        activity_factory(
            employee=employee,
            direction=AttendanceActivity.Direction.UNKNOWN,
        )

        employee.refresh_from_db()
        self.assertEqual(employee.punch_status, "")
        self.assertIsNone(employee.punch_time)

    def test_unknown_punch_keeps_previous_mirror(self):
        employee = employee_factory(first_name="Hold", emp_code="PS103")

        activity_factory(
            employee=employee,
            direction=AttendanceActivity.Direction.IN,
        )
        activity_factory(
            employee=employee,
            direction=AttendanceActivity.Direction.UNKNOWN,
        )

        employee.refresh_from_db()
        self.assertEqual(employee.punch_status, AttendanceActivity.Direction.IN)

    def test_latest_punch_wins_tie_broken_by_id(self):
        employee = employee_factory(first_name="Two", emp_code="PS104")
        punch_time = timezone.now()

        activity_factory(
            employee=employee,
            punch_time=punch_time,
            direction=AttendanceActivity.Direction.IN,
        )
        employee.refresh_from_db()
        first_evaluated = employee.punch_status

        activity_factory(
            employee=employee,
            punch_time=punch_time,
            direction=AttendanceActivity.Direction.OUT,
        )
        employee.refresh_from_db()

        # Same second: the later row must mirror, never the earlier one.
        self.assertEqual(first_evaluated, AttendanceActivity.Direction.IN)
        self.assertEqual(employee.punch_status, AttendanceActivity.Direction.OUT)

    def test_idempotent_when_mirror_matches(self):
        employee = employee_factory(first_name="Idle", emp_code="PS105")

        activity_factory(
            employee=employee,
            direction=AttendanceActivity.Direction.IN,
        )
        stamp = employee.updated_at
        employee.refresh_from_db()

        employee_punch_status_recompute(employee=employee)

        employee.refresh_from_db()
        self.assertEqual(employee.updated_at, stamp)


class EmployeePunchStatusWritePathTests(BaseTenantTestCase):
    """The mirror stays honest across punch create/update/delete."""

    def test_activity_create_mirrors_punch(self):
        employee = employee_factory(first_name="Make", emp_code="PS200")

        activity_create(
            employee=employee,
            punch_time=timezone.now(),
            direction=AttendanceActivity.Direction.IN,
        )

        employee.refresh_from_db()
        self.assertEqual(employee.punch_status, AttendanceActivity.Direction.IN)

    def test_activity_update_recomputes(self):
        employee = employee_factory(first_name="Edit", emp_code="PS201")
        old_time = timezone.now()
        new_time = timezone.now() + timedelta(hours=2)

        activity = activity_create(
            employee=employee,
            punch_time=old_time,
            direction=AttendanceActivity.Direction.IN,
        )
        activity_create(
            employee=employee,
            punch_time=new_time,
            direction=AttendanceActivity.Direction.OUT,
        )
        # Editing the older punch cannot become the mirror: the newer
        # OUT is still the latest punch.
        activity_update(
            activity=activity,
            employee=employee,
            punch_time=old_time,
            direction=AttendanceActivity.Direction.BREAK_IN,
            method=AttendanceActivity.AttendanceActivityMethodType.MANUAL,
        )

        employee.refresh_from_db()
        self.assertEqual(employee.punch_status, AttendanceActivity.Direction.OUT)

    def test_editing_latest_punch_updates_mirror(self):
        employee = employee_factory(first_name="Flip", emp_code="PS202")
        punch_time = timezone.now()

        activity = activity_create(
            employee=employee,
            punch_time=punch_time,
            direction=AttendanceActivity.Direction.IN,
        )
        activity_update(
            activity=activity,
            employee=employee,
            punch_time=punch_time,
            direction=AttendanceActivity.Direction.BREAK_IN,
            method=AttendanceActivity.AttendanceActivityMethodType.MANUAL,
        )

        employee.refresh_from_db()
        self.assertEqual(
            employee.punch_status, AttendanceActivity.Direction.BREAK_IN
        )

    def test_delete_falls_back_to_previous_punch(self):
        employee = employee_factory(first_name="Undo", emp_code="PS203")
        first = activity_create(
            employee=employee,
            punch_time=timezone.now(),
            direction=AttendanceActivity.Direction.IN,
        )
        second = activity_create(
            employee=employee,
            punch_time=timezone.now() + timedelta(hours=1),
            direction=AttendanceActivity.Direction.OUT,
        )
        self.assertEqual(
            employee.punch_status, AttendanceActivity.Direction.OUT
        )

        activity_delete(activity=second)

        employee.refresh_from_db()
        self.assertEqual(employee.punch_status, AttendanceActivity.Direction.IN)
        self.assertEqual(employee.punch_time, first.punch_time)

    def test_delete_last_punch_clears_mirror(self):
        employee = employee_factory(first_name="Clear", emp_code="PS204")
        activity = activity_create(
            employee=employee,
            punch_time=timezone.now(),
            direction=AttendanceActivity.Direction.OUT,
        )

        activity_delete(activity=activity)

        employee.refresh_from_db()
        self.assertEqual(employee.punch_status, "")
        self.assertIsNone(employee.punch_time)

    def test_gateway_replay_does_not_rewrite_mirror(self):
        employee = employee_factory(first_name="Replay", emp_code="PS205")
        punch_time = timezone.now()

        first = activity_create(
            employee=employee,
            punch_time=punch_time,
            direction=AttendanceActivity.Direction.IN,
            external_id="gateway:42",
        )
        stamp = employee.updated_at
        second = activity_create(
            employee=employee,
            punch_time=punch_time + timedelta(hours=3),
            direction=AttendanceActivity.Direction.IN,
            external_id="gateway:42",
        )
        employee.refresh_from_db()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(employee.punch_status, AttendanceActivity.Direction.IN)
        self.assertEqual(employee.punch_time, punch_time)
        self.assertEqual(employee.updated_at, stamp)

    def test_employees_are_independent(self):
        alice = employee_factory(first_name="Alice", emp_code="PS206")
        bob = employee_factory(first_name="Bob", emp_code="PS207")

        activity_create(
            employee=bob,
            punch_time=timezone.now(),
            direction=AttendanceActivity.Direction.IN,
        )

        alice.refresh_from_db()
        self.assertEqual(alice.punch_status, "")
