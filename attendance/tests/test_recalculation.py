from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from django.utils import timezone

from attendance.calculation import direction_from_gateway_status_label
from attendance.models import Attendance, AttendanceActivity
from attendance.recalculation import recalculate_attendance
from attendance.services import activity_delete, device_attendance_pull
from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    attendance_record_factory,
    device_factory,
    employee_factory,
    schedule_factory,
    timetable_factory,
)
from companies.services import attendance_log_create
from schedule.models import EmployeeScheduleAssignment, EmployeeScheduleOverride

QATAR = ZoneInfo("Asia/Qatar")


def aware(year, month, day, hour, minute=0):
    from datetime import datetime

    return datetime(year, month, day, hour, minute, tzinfo=QATAR)


def assign(*, schedule, employee):
    assignment = EmployeeScheduleAssignment.objects.create(
        schedule=schedule,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    assignment.employees.add(employee)
    return assignment


class DirectionMappingTests(SimpleTestCase):
    def test_checkout_labels_map_to_out(self):
        # Mapping value/label ("Check Out") and key ("checkout") spellings
        # both resolve to the AttendanceActivity direction code "out".
        for label in ("Checkout", "Check Out", "check-out", "check_out", "CHECK OUT"):
            with self.subTest(label=label):
                self.assertEqual(direction_from_gateway_status_label(label), "out")

    def test_checkin_labels_map_to_in(self):
        for label in ("IN", "Check In", "checkin", "check-in", "check_in"):
            with self.subTest(label=label):
                self.assertEqual(direction_from_gateway_status_label(label), "in")

    def test_missing_or_unknown_labels_stay_unknown(self):
        for label in (None, "", "bogus", "Break Out"):
            with self.subTest(label=label):
                self.assertEqual(direction_from_gateway_status_label(label), "unknown")


class RecalculationTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        timezone.activate(QATAR)
        self.addCleanup(timezone.deactivate)
        device_factory(serial_number="ZK-001", company=self.tenant)
        self.employee = employee_factory(first_name="Recalc", emp_code="RC001")
        self.day = date(2026, 9, 2)  # Wednesday
        morning = timetable_factory(
            name="Morning",
            code="MORN-RC",
            check_in=time(9, 0),
            check_out=time(18, 0),
        )
        schedule = schedule_factory(name="Week Schedule", timetable=morning)
        assign(schedule=schedule, employee=self.employee)

    def push(self, *, at, status=0, gateway_log_id, emp_code="RC001"):
        return attendance_log_create(
            serial_number="ZK-001",
            employee_id=emp_code,
            gateway_log_id=gateway_log_id,
            timestamp=at,
            extra_raw_data={
                "status": status,
                "status_label": "Check Out" if status == 1 else "Check In",
                "verify_mode": 1,
            },
        )

    def daily(self):
        return Attendance.objects.get(employee=self.employee, day=self.day)

    def test_push_creates_present_daily_attendance(self):
        self.push(at=aware(2026, 9, 2, 9), gateway_log_id=1)
        self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=2)

        daily = self.daily()
        self.assertEqual(daily.status, Attendance.Status.PRESENT)
        self.assertTrue(daily.is_calculated)
        self.assertIsNotNone(daily.calculated_at)
        self.assertTrue(daily.has_check_in)
        self.assertTrue(daily.has_check_out)
        self.assertEqual(timezone.localtime(daily.first_in).hour, 9)
        self.assertEqual(timezone.localtime(daily.last_out).hour, 18)
        self.assertEqual(daily.worked_minutes, 540)
        self.assertEqual(daily.late_minutes, 0)
        self.assertEqual(daily.early_leave_minutes, 0)
        self.assertIsNotNone(daily.shift)
        self.assertEqual(daily.activities.count(), 2)

    def test_late_punch_marks_late(self):
        self.push(at=aware(2026, 9, 2, 9, 30), gateway_log_id=11)
        self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=12)

        daily = self.daily()
        self.assertEqual(daily.status, Attendance.Status.LATE)
        self.assertEqual(daily.late_minutes, 30)

    def test_early_out_marks_early_out(self):
        self.push(at=aware(2026, 9, 2, 9), gateway_log_id=21)
        self.push(at=aware(2026, 9, 2, 17), status=1, gateway_log_id=22)

        daily = self.daily()
        self.assertEqual(daily.status, Attendance.Status.EARLY_OUT)
        self.assertEqual(daily.early_leave_minutes, 60)

    def test_single_punch_is_incomplete(self):
        # Label-less payload: direction falls back to UNKNOWN, no crash.
        attendance_log_create(
            serial_number="ZK-001",
            employee_id="RC001",
            gateway_log_id=31,
            timestamp=aware(2026, 9, 2, 9),
            extra_raw_data={"status": 0, "verify_mode": 1},
        )

        daily = self.daily()
        self.assertEqual(daily.status, Attendance.Status.INCOMPLETE)
        self.assertTrue(daily.has_check_in)
        self.assertFalse(daily.has_check_out)
        self.assertEqual(
            daily.activities.get().direction, AttendanceActivity.Direction.UNKNOWN
        )

    def test_split_day_spans_break_first_to_last(self):
        self.push(at=aware(2026, 9, 2, 9), gateway_log_id=41)
        self.push(at=aware(2026, 9, 2, 12), status=1, gateway_log_id=42)
        self.push(at=aware(2026, 9, 2, 13), gateway_log_id=43)
        self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=44)

        daily = self.daily()
        self.assertEqual(daily.status, Attendance.Status.PRESENT)
        # First-in/last-out: the full 09:00 -> 18:00 span counts as
        # worked (this timetable defines no breaks to deduct).
        self.assertEqual(daily.worked_minutes, 540)
        self.assertEqual(daily.activities.count(), 4)

    def test_duplicate_taps_within_window_count_once(self):
        self.push(at=aware(2026, 9, 2, 9, 0), gateway_log_id=51)
        self.push(at=datetime(2026, 9, 2, 9, 0, 30, tzinfo=QATAR), gateway_log_id=52)
        self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=53)

        daily = self.daily()
        self.assertEqual(daily.worked_minutes, 540)
        # All three punches are linked; pairing deduped the double-tap.
        self.assertEqual(daily.activities.count(), 3)

    def test_replay_keeps_single_daily_row(self):
        first = self.push(at=aware(2026, 9, 2, 9), gateway_log_id=61)
        second = self.push(at=aware(2026, 9, 2, 9), gateway_log_id=61)

        self.assertEqual(first.id, second.id)
        self.assertEqual(
            Attendance.objects.filter(
                employee=self.employee, day=self.day
            ).count(),
            1,
        )

    def test_manual_record_is_never_overwritten(self):
        manual = attendance_record_factory(
            employee=self.employee,
            day=self.day,
            status=Attendance.Status.LEAVE,
        )
        self.assertFalse(manual.is_calculated)

        self.push(at=aware(2026, 9, 2, 9), gateway_log_id=71)
        self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=72)

        manual.refresh_from_db()
        self.assertEqual(manual.status, Attendance.Status.LEAVE)
        self.assertFalse(manual.is_calculated)

    def test_delete_punch_recalculates_day(self):
        self.push(at=aware(2026, 9, 2, 9), gateway_log_id=81)
        out = self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=82)
        self.assertEqual(self.daily().status, Attendance.Status.PRESENT)

        activity_delete(activity=out)

        self.assertEqual(self.daily().status, Attendance.Status.INCOMPLETE)

    def test_day_off_punch_is_present_with_overtime(self):
        friday = date(2026, 9, 4)
        EmployeeScheduleOverride.objects.create(
            employee=self.employee, date=friday, is_day_off=True
        )
        self.push(at=aware(2026, 9, 4, 10), gateway_log_id=91)
        self.push(at=aware(2026, 9, 4, 14), status=1, gateway_log_id=92)

        daily = Attendance.objects.get(employee=self.employee, day=friday)
        self.assertEqual(daily.status, Attendance.Status.PRESENT)
        self.assertEqual(daily.worked_minutes, 240)
        self.assertEqual(daily.overtime_minutes, 240)


class OvernightRecalculationTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        timezone.activate(QATAR)
        self.addCleanup(timezone.deactivate)
        device_factory(serial_number="ZK-001", company=self.tenant)
        self.employee = employee_factory(first_name="Night", emp_code="RC900")
        self.monday = date(2026, 3, 9)
        night = timetable_factory(
            name="Night",
            code="NIGHT-RC",
            check_in=time(22, 0),
            check_out=time(6, 0),
            check_out_cross_days=1,
        )
        schedule = schedule_factory(name="Night Schedule", timetable=night)
        assign(schedule=schedule, employee=self.employee)

    def test_overnight_checkout_belongs_to_shift_day(self):
        attendance_log_create(
            serial_number="ZK-001",
            employee_id="RC900",
            gateway_log_id=101,
            timestamp=aware(2026, 3, 9, 21, 55),
            extra_raw_data={"status": 0, "status_label": "Check In"},
        )
        attendance_log_create(
            serial_number="ZK-001",
            employee_id="RC900",
            gateway_log_id=102,
            timestamp=aware(2026, 3, 10, 6, 10),
            extra_raw_data={"status": 1, "status_label": "Check Out"},
        )

        daily = Attendance.objects.get(employee=self.employee, day=self.monday)
        self.assertEqual(daily.status, Attendance.Status.PRESENT)
        self.assertEqual(daily.worked_minutes, 495)
        self.assertFalse(
            Attendance.objects.filter(
                employee=self.employee, day=date(2026, 3, 10)
            ).exists()
        )


class PullRecalculationTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        timezone.activate(QATAR)
        self.addCleanup(timezone.deactivate)
        device_factory(serial_number="TEST001", company=self.tenant)
        employee_factory(first_name="Alice", emp_code="1001")

    @patch("attendance.services.device_gateway_attendance_fetch")
    def test_pull_recalculates_daily_attendance(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "id": 101,
                "user_id": "1001",
                "timestamp": "2026-09-02T06:00:00Z",  # 09:00 +03:00
                "status": 0,
                "status_label": "Check In",
                "verify_mode": 1,
                "work_code": "0",
            },
            {
                "id": 102,
                "user_id": "1001",
                "timestamp": "2026-09-02T15:00:00Z",  # 18:00 +03:00
                "status": 1,
                "status_label": "Check Out",
                "verify_mode": 1,
                "work_code": "0",
            },
        ]

        result = device_attendance_pull(serial_number="TEST001")

        self.assertEqual(result["created"], 2)
        daily = Attendance.objects.get(
            employee__emp_code="1001", day=date(2026, 9, 2)
        )
        self.assertEqual(daily.status, Attendance.Status.PRESENT)
        self.assertEqual(daily.worked_minutes, 540)
        # Second identical pull stays idempotent: one daily row.
        device_attendance_pull(serial_number="TEST001")
        self.assertEqual(
            Attendance.objects.filter(
                employee__emp_code="1001", day=date(2026, 9, 2)
            ).count(),
            1,
        )

    def test_recalculate_without_punches_returns_none(self):
        employee = employee_factory(first_name="Empty", emp_code="RCEMPTY")
        self.assertIsNone(
            recalculate_attendance(employee=employee, day=date(2026, 9, 2))
        )
