from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from django.utils import timezone

from attendance.calculation import (
    direction_from_gateway_status,
    pair_punches,
    summarize_pairs,
)
from attendance.models import AttendancePeriod, AttendanceTransaction, DailyAttendance
from attendance.services import (
    attendance_transaction_delete,
    device_attendance_pull,
    recalculate_daily_attendance,
)
from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    daily_attendance_factory,
    device_factory,
    employee_factory,
    timetable_factory,
)
from companies.services import attendance_log_create
from employees.models import Employee
from schedule.models import ScheduleAssignment
from schedule.services import schedule_assignment_create, shift_create

QATAR = ZoneInfo("Asia/Qatar")


def aware(year, month, day, hour, minute=0):
    from datetime import datetime

    return datetime(year, month, day, hour, minute, tzinfo=QATAR)


class DirectionMappingTests(SimpleTestCase):
    def test_explicit_checkout_statuses_map_to_out(self):
        for status in (1, 2, 5, "1"):
            with self.subTest(status=status):
                self.assertEqual(direction_from_gateway_status(status), "out")

    def test_checkin_and_unknown_statuses_stay_unknown(self):
        # Most devices report every punch as 0: keep UNKNOWN so the
        # first punch still pairs as check-in.
        for status in (0, 3, 4, 99, None, "", "bogus"):
            with self.subTest(status=status):
                self.assertEqual(direction_from_gateway_status(status), "unknown")


class PairingTests(SimpleTestCase):
    def punch(self, at, direction="unknown"):
        # Unsaved instances: pairing only reads timestamp/direction.
        return AttendanceTransaction(
            employee=Employee(),
            external_id=f"pair-{at.isoformat()}",
            timestamp=at,
            direction=direction,
            source=AttendanceTransaction.Source.MANUAL,
        )

    def test_unknown_punches_alternate_in_out(self):
        pairs = pair_punches(
            [
                self.punch(aware(2026, 9, 2, 9)),
                self.punch(aware(2026, 9, 2, 18)),
            ]
        )
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][0].timestamp, aware(2026, 9, 2, 9))
        self.assertEqual(pairs[0][1].timestamp, aware(2026, 9, 2, 18))

    def test_explicit_out_closes_open_in(self):
        pairs = pair_punches(
            [
                self.punch(aware(2026, 9, 2, 9)),
                self.punch(aware(2026, 9, 2, 12), direction="out"),
                self.punch(aware(2026, 9, 2, 13)),
                self.punch(aware(2026, 9, 2, 18), direction="out"),
            ]
        )
        self.assertEqual(len(pairs), 2)
        self.assertTrue(all(c is not None and o is not None for c, o in pairs))

    def test_summary_totals_first_last_and_break(self):
        summary = summarize_pairs(
            pair_punches(
                [
                    self.punch(aware(2026, 9, 2, 9)),
                    self.punch(aware(2026, 9, 2, 12), direction="out"),
                    self.punch(aware(2026, 9, 2, 13)),
                    self.punch(aware(2026, 9, 2, 18), direction="out"),
                ]
            )
        )
        self.assertTrue(summary.has_check_in)
        self.assertTrue(summary.has_check_out)
        self.assertEqual(summary.first_in, aware(2026, 9, 2, 9))
        self.assertEqual(summary.last_out, aware(2026, 9, 2, 18))
        self.assertEqual(summary.worked_minutes, 480)
        self.assertEqual(summary.break_minutes, 60)


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
        shift = shift_create(
            name="Week Shift",
            code="WEEK-RC",
            cycle_unit="week",
            shift_days=[{"day_number": self.day.isoweekday(), "timetable": morning}],
        )
        schedule_assignment_create(
            assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
            shift=shift,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            employee=self.employee,
        )

    def push(self, *, at, status=0, gateway_log_id, emp_code="RC001"):
        return attendance_log_create(
            serial_number="ZK-001",
            employee_id=emp_code,
            gateway_log_id=gateway_log_id,
            timestamp=at,
            extra_raw_data={"status": status, "verify_mode": 1},
        )

    def daily(self):
        return DailyAttendance.objects.get(employee=self.employee, date=self.day)

    def test_push_creates_present_daily_attendance(self):
        self.push(at=aware(2026, 9, 2, 9), gateway_log_id=1)
        self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=2)

        daily = self.daily()
        self.assertEqual(daily.status, DailyAttendance.Status.PRESENT)
        self.assertTrue(daily.is_calculated)
        self.assertIsNotNone(daily.calculated_at)
        self.assertTrue(daily.has_check_in)
        self.assertTrue(daily.has_check_out)
        self.assertEqual(timezone.localtime(daily.first_in).hour, 9)
        self.assertEqual(timezone.localtime(daily.last_out).hour, 18)
        self.assertEqual(daily.scheduled_minutes, 540)
        self.assertEqual(daily.worked_minutes, 540)
        self.assertEqual(daily.late_minutes, 0)
        self.assertEqual(daily.early_leave_minutes, 0)
        self.assertIsNotNone(daily.timetable)
        self.assertIsNotNone(daily.shift)

        periods = list(daily.periods.all())
        self.assertEqual(len(periods), 1)
        self.assertTrue(periods[0].is_valid)
        self.assertEqual(periods[0].worked_minutes, 540)

    def test_late_punch_marks_late(self):
        self.push(at=aware(2026, 9, 2, 9, 30), gateway_log_id=11)
        self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=12)

        daily = self.daily()
        self.assertEqual(daily.status, DailyAttendance.Status.LATE)
        self.assertEqual(daily.late_minutes, 30)

    def test_early_out_marks_early_out(self):
        self.push(at=aware(2026, 9, 2, 9), gateway_log_id=21)
        self.push(at=aware(2026, 9, 2, 17), status=1, gateway_log_id=22)

        daily = self.daily()
        self.assertEqual(daily.status, DailyAttendance.Status.EARLY_OUT)
        self.assertEqual(daily.early_leave_minutes, 60)

    def test_single_punch_is_incomplete(self):
        self.push(at=aware(2026, 9, 2, 9), gateway_log_id=31)

        daily = self.daily()
        self.assertEqual(daily.status, DailyAttendance.Status.INCOMPLETE)
        self.assertTrue(daily.has_check_in)
        self.assertFalse(daily.has_check_out)

    def test_split_day_pairs_two_periods_with_break(self):
        self.push(at=aware(2026, 9, 2, 9), gateway_log_id=41)
        self.push(at=aware(2026, 9, 2, 12), status=1, gateway_log_id=42)
        self.push(at=aware(2026, 9, 2, 13), gateway_log_id=43)
        self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=44)

        daily = self.daily()
        self.assertEqual(daily.status, DailyAttendance.Status.PRESENT)
        self.assertEqual(daily.worked_minutes, 480)
        self.assertEqual(daily.break_minutes, 60)
        self.assertEqual(daily.periods.count(), 2)

    def test_duplicate_taps_within_window_count_once(self):
        self.push(at=aware(2026, 9, 2, 9, 0), gateway_log_id=51)
        self.push(
            at=datetime(2026, 9, 2, 9, 0, 30, tzinfo=QATAR), gateway_log_id=52
        )
        self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=53)

        daily = self.daily()
        self.assertEqual(daily.periods.count(), 1)
        self.assertEqual(daily.worked_minutes, 540)

    def test_replay_keeps_single_daily_row(self):
        first = self.push(at=aware(2026, 9, 2, 9), gateway_log_id=61)
        second = self.push(at=aware(2026, 9, 2, 9), gateway_log_id=61)

        self.assertEqual(first.id, second.id)
        self.assertEqual(
            DailyAttendance.objects.filter(
                employee=self.employee, date=self.day
            ).count(),
            1,
        )

    def test_manual_record_is_never_overwritten(self):
        manual = daily_attendance_factory(
            employee=self.employee,
            date=self.day,
            status=DailyAttendance.Status.LEAVE,
        )
        self.assertFalse(manual.is_calculated)

        self.push(at=aware(2026, 9, 2, 9), gateway_log_id=71)
        self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=72)

        manual.refresh_from_db()
        self.assertEqual(manual.status, DailyAttendance.Status.LEAVE)
        self.assertFalse(manual.is_calculated)

    def test_delete_punch_recalculates_day(self):
        self.push(at=aware(2026, 9, 2, 9), gateway_log_id=81)
        out = self.push(at=aware(2026, 9, 2, 18), status=1, gateway_log_id=82)
        self.assertEqual(self.daily().status, DailyAttendance.Status.PRESENT)

        attendance_transaction_delete(transaction=out)

        self.assertEqual(self.daily().status, DailyAttendance.Status.INCOMPLETE)
        self.assertEqual(AttendancePeriod.objects.filter(
            daily_attendance=self.daily()
        ).count(), 1)

    def test_day_off_punch_is_worked_holiday(self):
        off = timetable_factory(
            name="Friday Off",
            code="OFF-RC",
            work_type="off",
            check_in=None,
            check_out=None,
        )
        friday = date(2026, 9, 4)
        shift = shift_create(
            name="Friday Off Shift",
            code="OFF-RC-SHIFT",
            cycle_unit="week",
            shift_days=[{"day_number": friday.isoweekday(), "timetable": off}],
        )
        schedule_assignment_create(
            assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
            shift=shift,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            employee=self.employee,
        )
        self.push(at=aware(2026, 9, 4, 10), gateway_log_id=91)
        self.push(at=aware(2026, 9, 4, 14), status=1, gateway_log_id=92)

        daily = DailyAttendance.objects.get(employee=self.employee, date=friday)
        self.assertEqual(daily.status, DailyAttendance.Status.WORKED_HOLIDAY)
        self.assertEqual(daily.worked_minutes, 240)


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
        shift = shift_create(
            name="Monday Nights",
            code="NIGHT-RC-SHIFT",
            cycle_unit="week",
            shift_days=[{"day_number": 1, "timetable": night}],
        )
        schedule_assignment_create(
            assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
            shift=shift,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            employee=self.employee,
        )

    def test_overnight_checkout_belongs_to_shift_day(self):
        attendance_log_create(
            serial_number="ZK-001",
            employee_id="RC900",
            gateway_log_id=101,
            timestamp=aware(2026, 3, 9, 21, 55),
            extra_raw_data={"status": 0},
        )
        attendance_log_create(
            serial_number="ZK-001",
            employee_id="RC900",
            gateway_log_id=102,
            timestamp=aware(2026, 3, 10, 6, 10),
            extra_raw_data={"status": 1},
        )

        daily = DailyAttendance.objects.get(
            employee=self.employee, date=self.monday
        )
        self.assertEqual(daily.status, DailyAttendance.Status.PRESENT)
        self.assertEqual(daily.worked_minutes, 495)
        self.assertFalse(
            DailyAttendance.objects.filter(
                employee=self.employee, date=date(2026, 3, 10)
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
                "verify_mode": 1,
                "work_code": "0",
            },
            {
                "id": 102,
                "user_id": "1001",
                "timestamp": "2026-09-02T15:00:00Z",  # 18:00 +03:00
                "status": 1,
                "verify_mode": 1,
                "work_code": "0",
            },
        ]

        result = device_attendance_pull(serial_number="TEST001")

        self.assertEqual(result["created"], 2)
        daily = DailyAttendance.objects.get(
            employee__emp_code="1001", date=date(2026, 9, 2)
        )
        self.assertEqual(daily.status, DailyAttendance.Status.PRESENT)
        self.assertEqual(daily.worked_minutes, 540)
        # Second identical pull stays idempotent: one daily row.
        device_attendance_pull(serial_number="TEST001")
        self.assertEqual(
            DailyAttendance.objects.filter(
                employee__emp_code="1001", date=date(2026, 9, 2)
            ).count(),
            1,
        )

    def test_recalculate_without_punches_returns_none(self):
        employee = employee_factory(first_name="Empty", emp_code="RCEMPTY")
        self.assertIsNone(
            recalculate_daily_attendance(employee=employee, day=date(2026, 9, 2))
        )
