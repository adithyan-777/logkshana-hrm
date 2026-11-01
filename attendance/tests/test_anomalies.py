from datetime import date, datetime, timedelta

from django.urls import reverse
from django.utils.http import urlencode

from attendance.models import AttendanceActivity, WorkSession
from attendance.selectors import attendance_exception_day_list
from attendance.services import activity_correction_create
from common.tests.base import BaseTenantTestCase
from common.tests.factories import activity_factory, employee_factory
from policies.models import AttendancePolicy

DAY = date(2026, 11, 2)


class ExceptionQueueTestMixin:
    def _punch(self, *, external_id, direction, when, employee=None, **kwargs):
        return activity_factory(
            external_id=external_id,
            method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
            direction=direction,
            punch_time=when,
            employee=employee,
            **kwargs,
        )

    def _dt(self, day, hour, minute=0):
        return datetime(
            day.year,
            day.month,
            day.day,
            hour,
            minute,

        )

    def _unscheduled(self):
        AttendancePolicy.objects.get_or_create(
            schedule_mode=AttendancePolicy.ScheduleMode.UNSCHEDULED
        )


class ExceptionDayListTests(ExceptionQueueTestMixin, BaseTenantTestCase):
    """One exception = one (employee, day) with punch-flow problems."""

    def setUp(self):
        super().setUp()
        self._unscheduled()

    def test_groups_one_day_into_one_entry_with_all_problems(self):
        employee = employee_factory(first_name="Grouper", emp_code="EX-G1")
        self._punch(
            external_id="ex:in", direction="in", when=self._dt(DAY, 9),
            employee=employee,
        )
        # Duplicate IN while the session is open: absorbed (ignored).
        self._punch(
            external_id="ex:dup", direction="in", when=self._dt(DAY, 10),
            employee=employee,
        )
        self._punch(
            external_id="ex:out", direction="out", when=self._dt(DAY, 17),
            employee=employee,
        )
        # OUT after the session closed: stray (ignored).
        self._punch(
            external_id="ex:stray", direction="out", when=self._dt(DAY, 19),
            employee=employee,
        )

        entries = attendance_exception_day_list()

        mine = [e for e in entries if e["employee"].pk == employee.pk]
        self.assertEqual(len(mine), 1)
        entry = mine[0]
        self.assertEqual(entry["day"], DAY)
        self.assertEqual(len(entry["duplicate_ins"]), 1)
        self.assertEqual(len(entry["stray_outs"]), 1)
        # 17:00 OUT closed the session; no open session remains.
        self.assertFalse(entry["open_sessions"])
        self.assertTrue(entry["has_problems"])

    def test_todays_open_session_is_not_an_exception(self):
        today = date.today()
        employee = employee_factory(first_name="Today", emp_code="EX-T1")
        self._punch(
            external_id="ex:today-in", direction="in",
            when=self._dt(today, 9), employee=employee,
        )
        self.assertTrue(
            WorkSession.objects.filter(
                employee=employee, check_out__isnull=True
            ).exists()
        )

        entries = attendance_exception_day_list()

        self.assertFalse([e for e in entries if e["employee"].pk == employee.pk])

    def test_missing_checkout_day_is_unresolved_then_resolved_by_correction(self):
        employee = employee_factory(first_name="Forgot", emp_code="EX-F1")
        punch = self._punch(
            external_id="ex:forgot-in", direction="in", when=self._dt(DAY, 9),
            employee=employee,
        )

        entries = attendance_exception_day_list()
        entry = next(e for e in entries if e["employee"].pk == employee.pk)
        self.assertEqual(len(entry["open_sessions"]), 1)
        self.assertTrue(entry["has_problems"])
        self.assertFalse(entry["resolved"])

        # Correcting the forgotten IN to OUT re-pairs the day: the open
        # session disappears and the day flips to resolved (the ignored
        # correction row itself never counts as an exception).
        activity_correction_create(
            original=punch, direction=AttendanceActivity.Direction.OUT
        )

        entries = attendance_exception_day_list(status="resolved")
        entry = next(e for e in entries if e["employee"].pk == employee.pk)
        self.assertFalse(entry["open_sessions"])
        self.assertTrue(entry["resolved"])
        self.assertEqual(entry["corrected"][0].direction, "in")


class AnomalyViewTests(ExceptionQueueTestMixin, BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self._unscheduled()

    def test_queue_renders_with_summary_and_action_link(self):
        employee = employee_factory(first_name="Queue", emp_code="EX-Q1")
        self._punch(
            external_id="ex:q-in", direction="in", when=self._dt(DAY, 9),
            employee=employee,
        )

        response = self.client.get(
            reverse("attendance_anomalies"), HTTP_HX_REQUEST="true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check out missing")
        self.assertContains(response, "unresolved")
        # One-click path to the correction flow: pre-filtered punches tab.
        self.assertContains(
            response,
            reverse("attendance_transaction_list") + "?" + urlencode({"q": "EX-Q1"}),
        )

    def test_status_filter_resolved_only(self):
        response = self.client.get(
            reverse("attendance_anomalies") + "?status=resolved",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No punch-flow exceptions")

    def test_search_filters_by_employee(self):
        employee = employee_factory(first_name="Zeta", emp_code="EX-Z1")
        yesterday = date.today() - timedelta(days=1)
        self._punch(
            external_id="ex:z-in", direction="in",
            when=self._dt(yesterday, 9), employee=employee,
        )

        response = self.client.get(
            reverse("attendance_anomalies") + "?q=Zeta", HTTP_HX_REQUEST="true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Zeta")
        self.assertContains(response, "Check out missing")
