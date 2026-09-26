"""Cross-app integration: schedule + breaks + assignments + punches.

Covers (schedule, employees, attendance) together on one fixture:
timetable 09:00-18:00 with Lunch 13:00-14:00 and Tea 16:00-16:15,
plus an overnight 22:00-06:00 timetable with a 02:00-02:30 break.

Report-only suite: failures are reported, app code is not changed here.
"""

from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity
from attendance.recalculation import calculate_attendance, recalculate_attendance
from attendance.services import activity_create
from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    department_factory,
    employee_factory,
    schedule_factory,
    timetable_factory,
)
from schedule.models import EmployeeScheduleAssignment
from schedule.services import (
    assignment_create,
    resolve_assignment_employees,
    timetable_break_create,
)

DAY = date(2026, 3, 9)  # a Monday
NIGHT_DAY = date(2026, 3, 16)  # a Monday


def aware_at(day: date, at: time) -> datetime:
    return timezone.make_aware(datetime.combine(day, at))


def punch(employee, day, hour, minute=0, direction="unknown", tag=""):
    return activity_create(
        employee=employee,
        punch_time=aware_at(day, time(hour, minute)),
        direction=direction,
        external_id=f"XAPP-{employee.emp_code}-{tag or f'{hour:02d}{minute:02d}'}",
    )


class ScheduleBreaksE2EFixture(BaseTenantTestCase):
    """Shared fixture; subclasses add punch variants per test."""

    def setUp(self):
        super().setUp()
        self.timetable = timetable_factory(
            name="Office",
            code="XAPP-OFF",
            check_in=time(9, 0),
            check_out=time(18, 0),
        )
        timetable_break_create(
            timetable=self.timetable,
            name="Lunch",
            start_time=time(13, 0),
            end_time=time(14, 0),
        )
        timetable_break_create(
            timetable=self.timetable,
            name="Tea",
            start_time=time(16, 0),
            end_time=time(16, 15),
        )
        self.schedule = schedule_factory(
            name="XAPP Week", timetable=self.timetable
        )

        engineering = department_factory(name="Engineering", code="ENG")
        self.alice = employee_factory(
            first_name="Alice", emp_code="X001", department=engineering
        )
        self.bob = employee_factory(
            first_name="Bob", emp_code="X002", department=engineering
        )
        self.cara = employee_factory(first_name="Cara", emp_code="X003")
        self.dan = employee_factory(first_name="Dan", emp_code="X004")

        members = resolve_assignment_employees(
            mode="department", departments=[engineering]
        )
        self.assertEqual({e.pk for e in members}, {self.alice.pk, self.bob.pk})
        assignment_create(
            schedule=self.schedule,
            employees=members,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        assignment_create(
            schedule=self.schedule,
            employees=resolve_assignment_employees(
                mode="all_except", excluded=[self.alice, self.bob, self.dan]
            ),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        # Dan is left without any assignment on purpose (absent control).


class BreakValidationTests(ScheduleBreaksE2EFixture):
    def test_break_outside_work_hours_rejected(self):
        with self.assertRaises(ValidationError):
            timetable_break_create(
                timetable=self.timetable,
                name="Night",
                start_time=time(19, 0),
                end_time=time(20, 0),
            )

    def test_overlapping_breaks_rejected_on_timetable_add(self):
        data = {
            "name": "Overlap",
            "code": "OV1",
            "type": "normal",
            "check_in": "09:00",
            "check_out": "18:00",
            "check_out_cross_days": "",
            "work_minutes": "",
            "check_in_start": "",
            "check_in_end": "",
            "grace_period_minutes": "",
            "breaks-TOTAL_FORMS": "2",
            "breaks-INITIAL_FORMS": "0",
            "breaks-MIN_NUM_FORMS": "0",
            "breaks-MAX_NUM_FORMS": "1000",
            "breaks-0-name": "First",
            "breaks-0-break_time_type": "fixed",
            "breaks-0-break_time_minutes": "",
            "breaks-0-start_time": "13:00",
            "breaks-0-end_time": "14:00",
            "breaks-1-name": "Second",
            "breaks-1-break_time_type": "fixed",
            "breaks-1-break_time_minutes": "",
            "breaks-1-start_time": "13:30",
            "breaks-1-end_time": "14:30",
        }
        response = self.client.post(reverse("timetable_add"), data)

        self.assertIsNone(response.headers.get("HX-Trigger"))
        self.assertContains(response, "must not overlap")

    def test_boundary_break_accepted(self):
        edge = timetable_break_create(
            timetable=self.timetable,
            name="Edge",
            start_time=time(12, 0),
            end_time=time(13, 0),
        )
        self.assertEqual(self.timetable.breaks.count(), 3)
        edge.delete()


class PunchVariantTests(ScheduleBreaksE2EFixture):
    def _row(self, employee, day=DAY):
        return Attendance.objects.get(employee=employee, day=day)

    def test_full_day_with_break_punches(self):
        for at in [(9, 0), (13, 0), (14, 0), (16, 0), (16, 15), (18, 0)]:
            punch(self.alice, DAY, *at)
        row = self._row(self.alice)

        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.worked_minutes, 240 + 120 + 105)
        self.assertEqual(row.overtime_minutes, 0)

    def test_straight_through_day_earns_overtime(self):
        punch(self.bob, DAY, 9, 0, direction="in")
        punch(self.bob, DAY, 18, 0, direction="out")
        row = self._row(self.bob)

        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.worked_minutes, 540)
        self.assertEqual(row.overtime_minutes, 75)

    def test_late_arrival(self):
        punch(self.alice, DAY, 9, 20, direction="in")
        punch(self.alice, DAY, 18, 0, direction="out")
        row = self._row(self.alice)

        self.assertEqual(row.status, Attendance.Status.LATE)
        self.assertEqual(row.late_minutes, 20)

    def test_early_out(self):
        punch(self.bob, DAY, 9, 0, direction="in")
        punch(self.bob, DAY, 17, 0, direction="out")
        row = self._row(self.bob)

        self.assertEqual(row.status, Attendance.Status.EARLY_OUT)
        self.assertEqual(row.early_leave_minutes, 60)

    def test_single_punch_is_incomplete(self):
        punch(self.cara, DAY, 9, 0, direction="in")

        row = recalculate_attendance(employee=self.cara, day=DAY)

        self.assertEqual(row.status, Attendance.Status.INCOMPLETE)

    def test_no_punch_is_absent(self):
        result = calculate_attendance(day=DAY)

        self.assertIn(self.alice, result["absentees"])
        absent_row = Attendance.objects.get(employee=self.alice, day=DAY)
        self.assertEqual(absent_row.status, Attendance.Status.ABSENT)
        # Dan has no assignment at all: nothing is recorded for him.
        self.assertFalse(
            Attendance.objects.filter(employee=self.dan, day=DAY).exists()
        )

    def test_break_punch_outside_window_counts_as_normal_out(self):
        punch(self.alice, DAY, 9, 0, direction="in")
        punch(self.alice, DAY, 12, 0)  # before the 13:00 break window
        punch(self.alice, DAY, 18, 0, direction="out")
        row = self._row(self.alice)

        # Mid-day extra punch splits the day: (09:00, 12:00) worked,
        # lone 18:00 checkout closes nothing.
        self.assertEqual(row.worked_minutes, 180)
        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(timezone.localtime(row.last_out).time(), time(18, 0))

    def test_first_in_last_out_match_pairing(self):
        for at in [(9, 0), (13, 0), (14, 0), (18, 0)]:
            punch(self.bob, DAY, *at)
        row = self._row(self.bob)

        self.assertEqual(timezone.localtime(row.first_in).time(), time(9, 0))
        self.assertEqual(timezone.localtime(row.last_out).time(), time(18, 0))
        self.assertEqual(row.worked_minutes, 240 + 240)


class OvernightBreakTests(BaseTenantTestCase):
    def test_overnight_break_punches_stay_on_shift_day(self):
        night = timetable_factory(
            name="Night",
            code="XAPP-NGT",
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )
        timetable_break_create(
            timetable=night,
            name="Night break",
            start_time=time(2, 0),
            end_time=time(2, 30),
        )
        schedule = schedule_factory(name="XAPP Nights", timetable=night)
        owl = employee_factory(first_name="Owl", emp_code="X005")
        assignment = EmployeeScheduleAssignment.objects.create(
            schedule=schedule,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        assignment.employees.add(owl)

        punch(owl, NIGHT_DAY, 22, 0, direction="in")
        punch(owl, NIGHT_DAY + timedelta(days=1), 2, 0)
        punch(owl, NIGHT_DAY + timedelta(days=1), 2, 30)
        punch(owl, NIGHT_DAY + timedelta(days=1), 6, 10, direction="out")

        row = Attendance.objects.get(employee=owl, day=NIGHT_DAY)

        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.worked_minutes, 240 + 220)
        self.assertEqual(row.overtime_minutes, 10)

    def test_overnight_straight_through_earns_overtime(self):
        night = timetable_factory(
            name="Night",
            code="XAPP-NGT",
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )
        timetable_break_create(
            timetable=night,
            name="Night break",
            start_time=time(2, 0),
            end_time=time(2, 30),
        )
        schedule = schedule_factory(name="XAPP Nights", timetable=night)
        bat = employee_factory(first_name="Bat", emp_code="X006")
        assignment = EmployeeScheduleAssignment.objects.create(
            schedule=schedule,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        assignment.employees.add(bat)

        punch(bat, NIGHT_DAY, 22, 0, direction="in")
        punch(bat, NIGHT_DAY + timedelta(days=1), 6, 10, direction="out")

        row = Attendance.objects.get(employee=bat, day=NIGHT_DAY)

        self.assertEqual(row.status, Attendance.Status.PRESENT)
        self.assertEqual(row.worked_minutes, 490)
        self.assertEqual(row.overtime_minutes, 40)


class ReportsSurfaceTests(ScheduleBreaksE2EFixture):
    def test_reports_show_break_day(self):
        for at in [(9, 0), (13, 0), (14, 0), (18, 0)]:
            punch(self.alice, DAY, *at)
        month = {"date_from": "2026-03-01", "date_to": "2026-03-31"}

        summary = self.client.get(reverse("report_attendance_summary"), month)
        self.assertEqual(summary.status_code, 200)
        self.assertContains(summary, "Alice")

        log = self.client.get(reverse("report_punch_log"), month)
        self.assertEqual(log.status_code, 200)
        self.assertContains(log, "Alice")

        csv_response = self.client.get(
            reverse("report_attendance_summary"), {"format": "csv", **month}
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("Alice", csv_response.content.decode())
