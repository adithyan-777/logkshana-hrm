from unittest.mock import patch

from django.core.exceptions import ValidationError

from attendance.models import AttendanceActivity
from attendance.services import device_attendance_pull
from common.tests.base import BaseTenantTestCase
from common.tests.factories import device_factory, employee_factory
from companies.models import Device
from employees.models import Employee


SAMPLE_LOGS = [
    {
        "id": 101,
        "user_id": "1001",
        "timestamp": "2026-09-02T09:00:00Z",
        "status": 0,
        "verify_mode": 1,
        "work_code": "0",
        "serial_number": "TEST001",
    },
    {
        "id": 102,
        "user_id": "1001",
        "timestamp": "2026-09-02T17:30:00Z",
        "status": 0,
        "verify_mode": 1,
        "work_code": "0",
        "serial_number": "TEST001",
    },
]


class DeviceAttendancePullTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.device = device_factory(serial_number="TEST001", company=self.tenant)

    @patch("attendance.services.device_gateway_attendance_fetch")
    def test_creates_transactions_for_existing_employee(self, mock_fetch):
        employee_factory(first_name="Alice", emp_code="1001")
        mock_fetch.return_value = SAMPLE_LOGS

        result = device_attendance_pull(serial_number="TEST001")

        self.assertEqual(result["created"], 2)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["last_log_id"], 102)
        self.assertEqual(AttendanceActivity.objects.count(), 2)
        self.assertTrue(
            AttendanceActivity.objects.filter(external_id="gateway:101").exists()
        )

        self.device.refresh_from_db()
        self.assertEqual(self.device.last_gateway_log_id, 102)
        self.assertIsNotNone(self.device.last_synced_at)
        self.assertEqual(self.device.last_sync_error, "")

    @patch("attendance.services.device_gateway_attendance_fetch")
    def test_accepts_gateway_log_id_key(self, mock_fetch):
        """Real gateway payloads identify logs with gateway_log_id, not id."""
        employee_factory(first_name="Alice", emp_code="1001")
        mock_fetch.return_value = [
            {
                "gateway_log_id": 201,
                "user_id": "1001",
                "timestamp": "2026-09-02T09:00:00Z",
                "status": 0,
                "verify_mode": 1,
                "work_code": "0",
                "serial_number": "TEST001",
            }
        ]

        result = device_attendance_pull(serial_number="TEST001")

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["last_log_id"], 201)
        self.assertTrue(
            AttendanceActivity.objects.filter(external_id="gateway:201").exists()
        )

    @patch("attendance.services.device_gateway_attendance_fetch")
    def test_auto_creates_employee_when_missing(self, mock_fetch):
        mock_fetch.return_value = [SAMPLE_LOGS[0]]

        result = device_attendance_pull(serial_number="TEST001")

        self.assertEqual(result["created"], 1)
        employee = Employee.objects.get(emp_code="1001")
        self.assertEqual(employee.first_name, "Device")
        self.assertEqual(employee.last_name, "1001")

    @patch("attendance.services.device_gateway_attendance_fetch")
    def test_skips_existing_gateway_logs(self, mock_fetch):
        employee_factory(first_name="Alice", emp_code="1001")
        mock_fetch.return_value = SAMPLE_LOGS

        first = device_attendance_pull(serial_number="TEST001")
        second = device_attendance_pull(serial_number="TEST001")

        self.assertEqual(first["created"], 2)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["skipped"], 2)
        self.assertEqual(AttendanceActivity.objects.count(), 2)

    @patch("attendance.services.device_gateway_attendance_fetch")
    def test_uses_device_last_gateway_log_id_for_incremental_fetch(self, mock_fetch):
        self.device.last_gateway_log_id = 100
        self.device.save(update_fields=["last_gateway_log_id"])
        mock_fetch.return_value = []

        device_attendance_pull(serial_number="TEST001")

        mock_fetch.assert_called_once_with(
            serial_number="TEST001",
            after_id=100,
        )

    @patch("attendance.services.device_gateway_attendance_fetch")
    def test_rejects_unknown_device(self, mock_fetch):
        with self.assertRaises(ValidationError) as ctx:
            device_attendance_pull(serial_number="MISSING")

        self.assertIn("serial_number", ctx.exception.message_dict)
        mock_fetch.assert_not_called()

    @patch("attendance.services.device_gateway_attendance_fetch")
    def test_rejects_inactive_device(self, mock_fetch):
        self.device.is_active = False
        self.device.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError) as ctx:
            device_attendance_pull(serial_number="TEST001")

        self.assertIn("serial_number", ctx.exception.message_dict)
        mock_fetch.assert_not_called()

    @patch("attendance.services.device_gateway_attendance_fetch")
    def test_records_gateway_error_on_device(self, mock_fetch):
        mock_fetch.side_effect = ValidationError(
            {"device_gateway": "Gateway unreachable."}
        )

        with self.assertRaises(ValidationError):
            device_attendance_pull(serial_number="TEST001")

        self.device.refresh_from_db()
        self.assertIn("Gateway unreachable", self.device.last_sync_error)
