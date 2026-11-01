from django.urls import reverse

from attendance.models import Attendance, AttendanceActivity, WorkSession
from attendance.services import activity_correction_create
from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import activity_factory, employee_factory
from policies.models import AttendancePolicy


def _unschedule_tenant():
    """Flip the tenant policy to unscheduled (punch calculation on)."""
    AttendancePolicy.objects.get_or_create(
        schedule_mode=AttendancePolicy.ScheduleMode.UNSCHEDULED
    )


def _punch_at(day, hour, minute=0):
    """Aware punch time in the tenant timezone (punch days are local)."""
    from datetime import datetime

    return datetime(day.year, day.month, day.day, hour, minute)


class TransactionCorrectionTests(BaseTenantTestCase):
    """Biometric punches are corrected, not edited: a new punch with
    method=correction is added; the original stays untouched and points
    at its correction; the punch day is re-paired from the effective
    log (corrections replace their originals).
    """

    def _biometric_punch(self, *, external_id, **kwargs):
        defaults = {
            "method": AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
            "direction": AttendanceActivity.Direction.IN,
        }
        defaults.update(kwargs)
        punch = activity_factory(external_id=external_id, **defaults)
        punch.refresh_from_db()
        return punch

    def _login_as_plain_user(self, *, emp_code):
        employee = employee_factory(first_name="NoPerm", emp_code=emp_code)
        user = employee.user
        user.set_password(TEST_PASSWORD)
        user.save()
        self.login_as(user=user)
        return user

    # ------------------------------------------------------------------
    # Drawer step 1: impact review; step 2 (?step=form): direction-only
    # form with employee/time prepopulated read-only.
    # ------------------------------------------------------------------
    def test_get_htmx_renders_impact_review(self):
        punch = self._biometric_punch(external_id="gateway:corr-get")

        response = self.client.get(
            reverse("transaction_correct", args=[punch.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Work sessions to be rebuilt")
        self.assertContains(response, "Continue to correction")
        self.assertEqual(response.context["impact"]["days"], [punch.punch_time.date()])

    def test_get_step_form_renders_direction_only_form(self):
        punch = self._biometric_punch(external_id="gateway:corr-form")

        response = self.client.get(
            reverse("transaction_correct", args=[punch.pk]) + "?step=form",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Corrected direction")
        self.assertContains(
            response,
            punch.punch_time.strftime("%Y-%m-%d %H:%M"),
        )
        # Employee and punch time are inherited, not editable fields.
        self.assertNotContains(response, 'name="employee"')
        self.assertNotContains(response, 'name="punch_time"')

    def test_get_full_page_redirects_to_list_drawer(self):
        punch = self._biometric_punch(external_id="gateway:corr-page")

        response = self.client.get(reverse("transaction_correct", args=[punch.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("attendance_transaction_list"), response.url)
        self.assertIn("drawer=", response.url)

    # ------------------------------------------------------------------
    # POST: creates the correction row, links both ends, stamps the
    # audit trail, and re-pairs the punch day — the original never
    # changes.
    # ------------------------------------------------------------------
    def test_post_creates_correction_row_and_links(self):
        punch = self._biometric_punch(external_id="gateway:corr-post")

        response = self.client.post(
            reverse("transaction_correct", args=[punch.pk]),
            {
                "direction": AttendanceActivity.Direction.OUT,
                # Posted extras must be ignored: only direction is held.
                "punch_time": punch.punch_time.strftime("%Y-%m-%dT%H:%M")
                + ":55",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("transactionUpdated", response.headers.get("HX-Trigger", ""))
        correction = AttendanceActivity.objects.get(corrects=punch)
        self.assertEqual(
            correction.method,
            AttendanceActivity.AttendanceActivityMethodType.CORRECTION,
        )
        self.assertEqual(correction.direction, AttendanceActivity.Direction.OUT)
        self.assertEqual(correction.employee_id, punch.employee_id)
        self.assertEqual(correction.punch_time, punch.punch_time)
        self.assertTrue(correction.external_id.startswith("correction:"))
        self.assertEqual(correction.edited_by, self.user)
        # Original stays untouched (biometric, same direction/time) but
        # points at its correction.
        punch.refresh_from_db()
        self.assertEqual(
            punch.method, AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC
        )
        self.assertEqual(punch.direction, AttendanceActivity.Direction.IN)
        self.assertEqual(punch.corrected_punch_id, correction.pk)
        self.assertEqual(punch.corrected_at, punch.punch_time)

    def test_post_second_correction_is_refused(self):
        punch = self._biometric_punch(external_id="gateway:corr-dup")

        first = self.client.post(
            reverse("transaction_correct", args=[punch.pk]),
            {"direction": AttendanceActivity.Direction.OUT},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            reverse("transaction_correct", args=[punch.pk]),
            {"direction": AttendanceActivity.Direction.IN},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(second.status_code, 200)
        self.assertIn("showToast", second.headers.get("HX-Trigger", ""))
        self.assertEqual(
            AttendanceActivity.objects.filter(corrects=punch).count(), 1
        )

    def test_post_non_biometric_is_refused(self):
        punch = activity_factory(external_id="manual:corr-refused")

        response = self.client.post(
            reverse("transaction_correct", args=[punch.pk]),
            {"direction": AttendanceActivity.Direction.OUT},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("showToast", response.headers.get("HX-Trigger", ""))
        self.assertFalse(AttendanceActivity.objects.filter(corrects=punch).exists())

    def test_post_invalid_direction_re_renders_form_with_errors(self):
        punch = self._biometric_punch(external_id="gateway:corr-invalid")

        response = self.client.post(
            reverse("transaction_correct", args=[punch.pk]),
            {"direction": "nonsense"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("direction", response.context["form"].errors)
        self.assertFalse(AttendanceActivity.objects.filter(corrects=punch).exists())

    # ------------------------------------------------------------------
    # Guards: unknown PK, permissions, corrected state in the table.
    # ------------------------------------------------------------------
    def test_missing_id_404(self):
        response = self.client.get(reverse("transaction_correct", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_no_permission_forbidden(self):
        punch = self._biometric_punch(external_id="gateway:corr-403")
        self._login_as_plain_user(emp_code="COR-NOPERM")

        response = self.client.post(
            reverse("transaction_correct", args=[punch.pk]),
            {"direction": AttendanceActivity.Direction.OUT},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AttendanceActivity.objects.filter(corrects=punch).exists())

    def test_list_shows_correction_button_then_corrected_badge(self):
        punch = self._biometric_punch(external_id="gateway:corr-badge")
        list_url = reverse("attendance_transaction_list")

        before = self.client.get(list_url, HTTP_HX_REQUEST="true")
        self.assertContains(before, reverse("transaction_correct", args=[punch.pk]))
        self.assertNotContains(before, "status-corrected")

        self.client.post(
            reverse("transaction_correct", args=[punch.pk]),
            {"direction": AttendanceActivity.Direction.OUT},
            HTTP_HX_REQUEST="true",
        )

        after = self.client.get(list_url, HTTP_HX_REQUEST="true")
        self.assertContains(after, "Corrected")
        self.assertNotContains(after, reverse("transaction_correct", args=[punch.pk]))


class CorrectionRepairsWorkSessionsTests(BaseTenantTestCase):
    """Unscheduled-mode pairing: a correction replaces its original in
    the replay and the day's sessions/rows are re-derived.
    """

    def setUp(self):
        super().setUp()
        AttendancePolicy.objects.get_or_create(
            schedule_mode=AttendancePolicy.ScheduleMode.UNSCHEDULED
        )

    def _biometric_punch(self, *, external_id, direction, day):
        return activity_factory(
            external_id=external_id,
            method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
            direction=direction,
            punch_time=day,
        )

    def test_in_flip_to_out_rebuilds_day(self):
        """Forgotten punch-out story: only an IN ever arrived; flipping
        it to OUT must leave the day with no session and no check-in.
        """
        from datetime import date, datetime

        day = date(2026, 11, 2)
        punch = activity_factory(
            external_id="gateway:flip-in",
            method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
            direction=AttendanceActivity.Direction.IN,
            punch_time=datetime(2026, 11, 2, 9, 0),
        )
        self.assertTrue(
            WorkSession.objects.filter(employee=punch.employee, day=day).exists()
        )

        activity_correction_create(
            original=punch, direction=AttendanceActivity.Direction.OUT
        )

        self.assertFalse(
            WorkSession.objects.filter(employee=punch.employee, day=day).exists()
        )
        row = Attendance.objects.get(employee=punch.employee, day=day)
        self.assertIsNone(row.check_in)

    def test_stray_out_corrected_to_in_opens_session(self):
        """An OUT with nothing to close was ignored; correcting it to
        IN re-derives the day with a real check-in.
        """
        from datetime import date, datetime

        day = date(2026, 11, 2)
        punch = activity_factory(
            external_id="gateway:flip-out",
            method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
            direction=AttendanceActivity.Direction.OUT,
            punch_time=datetime(2026, 11, 2, 17, 0),
        )
        self.assertTrue(punch.ignored)

        activity_correction_create(
            original=punch, direction=AttendanceActivity.Direction.IN
        )

        session = WorkSession.objects.get(
            employee=punch.employee,
            day=day,
        )
        self.assertEqual(session.check_in, punch.punch_time)
        self.assertIsNone(session.check_out)
        row = Attendance.objects.get(employee=punch.employee, day=day)
        self.assertEqual(row.check_in, punch.punch_time)
        self.assertEqual(row.status, Attendance.Status.PRESENT)

    def test_repair_is_idempotent(self):
        "Running the repair twice keeps exactly one session."
        from datetime import date, datetime

        day = date(2026, 11, 2)
        punch = self._biometric_punch(
            external_id="gateway:repair-idem",
            direction=AttendanceActivity.Direction.IN,
            day=datetime(2026, 11, 2, 9, 0),
        )

        activity_correction_create(
            original=punch, direction=AttendanceActivity.Direction.IN
        )

        self.assertEqual(
            WorkSession.objects.filter(employee=punch.employee, day=day).count(), 1
        )
        ignored = AttendanceActivity.objects.filter(
            employee=punch.employee, ignored=True
        ).count()
        self.assertEqual(ignored, 0)


class CorrectionEdgeCaseTests(BaseTenantTestCase):
    """Edge cases of the direction-correction + day-repair logic."""

    def setUp(self):
        super().setUp()
        AttendancePolicy.objects.get_or_create(
            schedule_mode=AttendancePolicy.ScheduleMode.UNSCHEDULED
        )

    def _punch(self, *, external_id, direction, when, employee=None):
        return activity_factory(
            external_id=external_id,
            method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
            direction=direction,
            punch_time=when,
            employee=employee,
        )

    def _dt(self, day, hour, minute=0):
        from datetime import datetime

        return datetime(
            day.year,
            day.month,
            day.day,
            hour,
            minute,

        )

    def test_scheduled_tenant_correction_never_pairs(self):
        """In scheduled mode the punch log never pairs; a correction must
        not become a side door that suddenly builds work sessions."""
        from datetime import date

        from policies.models import AttendancePolicy as Policy

        Policy.objects.all().delete()  # back to scheduled (no policy row)
        day = date(2026, 11, 2)
        punch = self._punch(
            external_id="gateway:sched-in", direction="in", when=self._dt(day, 9)
        )
        self.assertEqual(WorkSession.objects.count(), 0)

        activity_correction_create(
            original=punch, direction=AttendanceActivity.Direction.OUT
        )

        self.assertEqual(WorkSession.objects.count(), 0)
        self.assertTrue(punch.corrected_punch_id)  # the log row still exists

    def test_late_night_punch_keeps_its_wall_clock_day(self):
        """A 00:30 local punch is stored 21:30 UTC the previous day.
        The repair must re-pair it onto the LOCAL day (as ingest did),
        not the UTC day."""
        from datetime import date

        day = date(2026, 11, 3)
        punch = self._punch(
            external_id="gateway:late-in", direction="in", when=self._dt(day, 0, 30)
        )
        session = WorkSession.objects.get(in_punch=punch)
        self.assertEqual(session.day, day)  # ingest attribution

        activity_correction_create(
            original=punch, direction=AttendanceActivity.Direction.IN
        )

        session = WorkSession.objects.get(
            in_punch__isnull=False, employee=punch.employee
        )
        self.assertEqual(session.day, day)  # replay keeps the same day

    def test_orphan_open_session_survives_repair(self):
        """An open session whose IN punch was deleted cannot be rebuilt
        from the log; the repair must keep it instead of wiping it."""
        from datetime import date

        from attendance.services import worksession_repair_for_employee_day

        day = date(2026, 11, 2)
        employee = employee_factory(first_name="Orphan", emp_code="ORPH1")
        punch = self._punch(
            external_id="gateway:orphan-in",
            direction="in",
            when=self._dt(day, 9),
            employee=employee,
        )
        orphan = WorkSession.objects.get(in_punch=punch)
        # Delete the punch (allowed for manual rows): the session keeps
        # its frozen times with in_punch NULL.
        punch.delete()
        orphan.refresh_from_db()
        self.assertIsNone(orphan.in_punch)

        worksession_repair_for_employee_day(employee=employee, day=day)

        self.assertTrue(
            WorkSession.objects.filter(pk=orphan.pk).exists(),
            "orphan open session must survive the repair",
        )

    def test_break_sessions_are_not_destroyed_by_repair(self):
        """Nothing re-derives break sessions today; the repair must not
        delete them (unrecoverable data loss)."""
        from datetime import date

        from attendance.models import Attendance, BreakSession
        from attendance.services import worksession_repair_for_employee_day

        day = date(2026, 11, 2)
        employee = employee_factory(first_name="Breaks", emp_code="BRKS1")
        punch = self._punch(
            external_id="gateway:break-in",
            direction="in",
            when=self._dt(day, 9),
            employee=employee,
        )
        row = Attendance.objects.get(employee=employee, day=day)
        break_row = BreakSession.objects.create(
            employee=employee,
            attendance=row,
            day=day,
            break_in=punch.punch_time,
        )

        worksession_repair_for_employee_day(employee=employee, day=day)

        self.assertTrue(
            BreakSession.objects.filter(pk=break_row.pk).exists(),
            "break sessions must survive the repair",
        )


class ManualPunchEditDeleteRepairTests(BaseTenantTestCase):
    """Manual punch edits/deletes re-pair their affected days — the
    same repair the correction flow uses, so no stale sessions or
    frozen check-in/out times survive an edit.
    """

    def setUp(self):
        super().setUp()
        AttendancePolicy.objects.get_or_create(
            schedule_mode=AttendancePolicy.ScheduleMode.UNSCHEDULED
        )

    def _punch(self, *, external_id, direction, when, employee=None):
        return activity_factory(
            external_id=external_id,
            method=AttendanceActivity.AttendanceActivityMethodType.MANUAL,
            direction=direction,
            punch_time=when,
            employee=employee,
        )

    def _dt(self, day, hour, minute=0):
        from datetime import datetime

        return datetime(
            day.year,
            day.month,
            day.day,
            hour,
            minute,

        )

    def test_edit_moves_check_out_time(self):
        from datetime import date, timedelta

        from attendance.services import activity_update

        day = date(2026, 11, 2)
        employee = employee_factory(first_name="Mover", emp_code="MED1")
        in_punch = self._punch(
            external_id="man:in", direction="in", when=self._dt(day, 9),
            employee=employee,
        )
        out_punch = self._punch(
            external_id="man:out", direction="out", when=self._dt(day, 17),
            employee=employee,
        )

        activity_update(
            activity=out_punch,
            employee=employee,
            punch_time=self._dt(day, 15),
            direction=AttendanceActivity.Direction.OUT,
        )

        session = WorkSession.objects.get(in_punch=in_punch)
        self.assertEqual(session.check_out, self._dt(day, 15))
        self.assertEqual(session.total_time, timedelta(hours=6))
        row = Attendance.objects.get(employee=employee, day=day)
        self.assertEqual(row.check_out, self._dt(day, 15))
        self.assertEqual(row.total_work_time, timedelta(hours=6))

    def test_edit_moves_punch_to_next_day_overnight_wrap(self):
        from datetime import date

        from attendance.services import activity_update

        day = date(2026, 11, 2)
        next_day = date(2026, 11, 3)
        employee = employee_factory(first_name="Night", emp_code="MED2")
        in_punch = self._punch(
            external_id="man:n-in", direction="in", when=self._dt(day, 22),
            employee=employee,
        )
        out_punch = self._punch(
            external_id="man:n-out", direction="out", when=self._dt(day, 23),
            employee=employee,
        )
        # Move the OUT to 02:00 next day (before any opening boundary):
        # the overnight session must wrap onto the next day.
        activity_update(
            activity=out_punch,
            employee=employee,
            punch_time=self._dt(next_day, 2),
            direction=AttendanceActivity.Direction.OUT,
        )

        session = WorkSession.objects.get(in_punch=in_punch)
        self.assertEqual(session.day, day)
        self.assertEqual(session.check_out, self._dt(next_day, 2))

    def test_edit_flips_direction(self):
        from datetime import date

        from attendance.services import activity_update

        day = date(2026, 11, 2)
        employee = employee_factory(first_name="Flip", emp_code="MED3")
        punch = self._punch(
            external_id="man:flip", direction="out", when=self._dt(day, 17),
            employee=employee,
        )
        self.assertTrue(punch.ignored)  # stray OUT at ingest

        activity_update(
            activity=punch,
            employee=employee,
            punch_time=self._dt(day, 17),
            direction=AttendanceActivity.Direction.IN,
        )

        punch.refresh_from_db()
        self.assertFalse(punch.ignored)  # replay recomputed the flag
        session = WorkSession.objects.get(in_punch=punch)
        self.assertEqual(session.check_in, self._dt(day, 17))

    def test_delete_out_punch_reopens_session(self):
        from datetime import date

        from attendance.services import activity_delete

        day = date(2026, 11, 2)
        employee = employee_factory(first_name="Deleter", emp_code="MED4")
        in_punch = self._punch(
            external_id="man:d-in", direction="in", when=self._dt(day, 9),
            employee=employee,
        )
        out_punch = self._punch(
            external_id="man:d-out", direction="out", when=self._dt(day, 17),
            employee=employee,
        )

        activity_delete(activity=out_punch)

        session = WorkSession.objects.get(in_punch=in_punch)
        self.assertIsNone(session.check_out)
        row = Attendance.objects.get(employee=employee, day=day)
        self.assertIsNone(row.check_out)

    def test_delete_in_punch_removes_session(self):
        from datetime import date

        from attendance.services import activity_delete

        day = date(2026, 11, 2)
        employee = employee_factory(first_name="DelIn", emp_code="MED5")
        in_punch = self._punch(
            external_id="man:di-in", direction="in", when=self._dt(day, 9),
            employee=employee,
        )
        self._punch(
            external_id="man:di-out", direction="out", when=self._dt(day, 17),
            employee=employee,
        )

        activity_delete(activity=in_punch)

        self.assertEqual(WorkSession.objects.filter(employee=employee).count(), 0)

    def test_scheduled_mode_edit_delete_never_pair(self):
        from datetime import date

        from attendance.services import activity_delete, activity_update
        from policies.models import AttendancePolicy as Policy

        Policy.objects.all().delete()  # scheduled (no policy row)
        day = date(2026, 11, 2)
        employee = employee_factory(first_name="Sched", emp_code="MED6")
        punch = self._punch(
            external_id="man:s-in", direction="in", when=self._dt(day, 9),
            employee=employee,
        )

        activity_update(
            activity=punch,
            employee=employee,
            punch_time=self._dt(day, 10),
            direction=AttendanceActivity.Direction.IN,
        )
        activity_delete(activity=punch)

        self.assertEqual(WorkSession.objects.filter(employee=employee).count(), 0)
