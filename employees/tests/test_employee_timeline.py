"""Render every timeline/day-grouping shape the detail page must survive.

Unscheduled-mode tenant with a paired work session, a manual break
session, an orphan punch (no attendance row), and a cross-day session,
then render the attendance tab as a full page and as both fragments,
plus a range-filtered view and the punch toggle. Guards the naive
wall-clock fixes (local_dt/local_date, plain TruncDate) — these exact
shapes crashed on timezone.localtime before them.
"""
from datetime import datetime, timedelta

from django.urls import reverse

from attendance.models import Attendance, AttendanceActivity, BreakSession
from attendance.services import activity_create
from common.localtime import local_date
from common.tests.base import BaseTenantTestCase
from common.tests.factories import employee_factory
from policies.models import AttendancePolicy

# Relative days so the fixture stays inside the detail view's default
# 7-day range (from today-6 to today) on every run date.
DAY = local_date()
NEXT_DAY = DAY + timedelta(days=1)


def _at(day, hour, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute)


def _punch(employee, when, direction):
    return activity_create(employee=employee, punch_time=when, direction=direction)


class TimelineRenderTests(BaseTenantTestCase):
    def test_attendance_tab_renders_all_timeline_shapes(self):
        # Unscheduled mode so punches pair into Attendance + work
        # sessions (the timeline data source). Scheduled mode keeps
        # punches as a pure log — covered by the other detail tests.
        AttendancePolicy.objects.create(
            schedule_mode=AttendancePolicy.ScheduleMode.UNSCHEDULED
        )
        employee = employee_factory(first_name="Sane", emp_code="SANITY1")
        # Paired work session 08:00-17:00, an orphan punch (no
        # attendance row) at 19:30, and a cross-day session 22:00->02:00.
        _punch(employee, _at(DAY, 8, 0), "in")
        _punch(employee, _at(DAY, 12, 0), "break_in")
        _punch(employee, _at(DAY, 12, 45), "break_out")
        _punch(employee, _at(DAY, 17, 0), "out")
        AttendanceActivity.objects.create(  # bypasses pairing: orphan
            employee=employee,
            punch_time=_at(DAY, 19, 30),
            direction="in",
            external_id="sanity-orphan",
        )
        _punch(employee, _at(DAY, 22, 0), "in")
        _punch(employee, _at(NEXT_DAY, 2, 0), "out")
        # The punch pipeline never derives BreakSessions (they're created
        # by device sync / manual entry — see test_punch_correction), so
        # add one directly to exercise the break-segment render path.
        attendance = Attendance.objects.get(employee=employee, day=DAY)
        BreakSession.objects.create(
            employee=employee,
            attendance=attendance,
            day=DAY,
            break_in=_at(DAY, 12, 0),
            break_out=_at(DAY, 12, 45),
        )

        url = reverse("employee_detail", args=[employee.pk])

        response = self.client.get(url, {"tab": "attendance"})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # Work segments: 08:00-17:00 and the cross-day session clipped
        # at 24:00; the manual break renders its own lane.
        self.assertIn("employee-detail__timeline-segment--work", body)
        self.assertIn("employee-detail__timeline-segment--break", body)
        self.assertIn("Work session · 22:00:00–24:00:00", body)
        self.assertIn("Includes next-day punches", body)
        self.assertIn("Present", body)

        response = self.client.get(
            url, {"tab": "attendance", "fragment": "detail"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="employee-detail-page"', response.content.decode())

        response = self.client.get(
            url, {"tab": "attendance", "fragment": "attendance"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="employee-attendance-region"', response.content.decode())

        # Explicit range exercises the TruncDate annotate + naive windows.
        response = self.client.get(
            url,
            {"tab": "attendance", "from": DAY.isoformat(), "to": NEXT_DAY.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Includes next-day punches", response.content.decode())

    def test_punch_toggle_updates_mirror(self):
        AttendancePolicy.objects.create(
            schedule_mode=AttendancePolicy.ScheduleMode.UNSCHEDULED
        )
        # Fresh employee, single unambiguously-past IN punch: the toggle
        # must record the inverse (OUT) and refresh the mirror. (Kept
        # separate from the timeline fixture above, whose today-dated
        # punches would make the mirrored state depend on wall-clock now.)
        employee = employee_factory(first_name="Togg", emp_code="SANITY2")
        _punch(employee, datetime(2020, 1, 1, 8, 0), "in")

        response = self.client.post(
            reverse("employee_punch_toggle", args=[employee.pk])
        )
        self.assertEqual(response.status_code, 200)
        employee.refresh_from_db()
        self.assertEqual(employee.punch_status, "out")
