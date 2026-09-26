from unittest.mock import patch

from django.core.exceptions import ValidationError
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.q2_tasks import fanout_device_sync, sync_device_attendance
from common.tests.base import BaseTenantTestCase
from common.tests.factories import device_factory


class SyncDeviceAttendanceTaskTests(BaseTenantTestCase):
    @patch("attendance.services.device_attendance_pull")
    def test_sync_one_delegates_to_service(self, mock_pull):
        device_factory(serial_number="TEST001", company=self.tenant)
        mock_pull.return_value = {"serial_number": "TEST001", "created": 1}

        result = sync_device_attendance("TEST001")

        mock_pull.assert_called_once_with(serial_number="TEST001")
        self.assertEqual(result["created"], 1)

    @patch("django_q.tasks.async_task")
    def test_fanout_enqueues_active_devices(self, mock_async):
        device_factory(serial_number="TEST001", company=self.tenant)
        device_factory(serial_number="TEST002", company=self.tenant, is_active=False)

        result = fanout_device_sync()

        self.assertEqual(result["devices"], 1)
        mock_async.assert_called_once()
        args, kwargs = mock_async.call_args
        self.assertEqual(args[0], "attendance.q2_tasks.sync_device_attendance")
        self.assertEqual(args[1], "TEST001")
        self.assertEqual(kwargs["group"], "device-sync")

    @patch("attendance.services.device_attendance_pull")
    def test_transient_error_schedules_retry(self, mock_pull):
        from django_q.models import Schedule

        mock_pull.side_effect = ValidationError(
            {"device_gateway": "Gateway 502 Bad Gateway"}
        )
        with schema_context(get_public_schema_name()):
            before = Schedule.objects.count()
            result = sync_device_attendance("TEST001")
            retries = list(Schedule.objects.all()[before:])

        self.assertTrue(result["retried"])
        self.assertEqual(result["attempt"], 1)
        self.assertEqual(len(retries), 1)
        self.assertEqual(retries[0].func, "attendance.q2_tasks.sync_device_attendance")

    @patch("attendance.services.device_attendance_pull")
    def test_permanent_error_raises_without_retry(self, mock_pull):
        from django_q.models import Schedule

        mock_pull.side_effect = ValidationError(
            {"serial_number": "Unknown device serial number."}
        )
        with schema_context(get_public_schema_name()):
            before = Schedule.objects.count()
            with self.assertRaises(ValidationError):
                sync_device_attendance("TEST001")
            after = Schedule.objects.count()

        self.assertEqual(before, after)

    @patch("attendance.services.device_attendance_pull")
    def test_retry_exhaustion_raises(self, mock_pull):
        from django_q.models import Schedule

        mock_pull.side_effect = ValidationError({"device_gateway": "timeout"})
        with schema_context(get_public_schema_name()):
            before = Schedule.objects.count()
            with self.assertRaises(ValidationError):
                sync_device_attendance("TEST001", attempt=3)
            after = Schedule.objects.count()

        self.assertEqual(mock_pull.call_count, 1)
        self.assertEqual(before, after)
