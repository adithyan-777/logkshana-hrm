from unittest.mock import patch

from django.test import override_settings

from attendance.tasks import device_attendance_sync_all_task, device_attendance_sync_task
from common.tests.base import BaseTenantTestCase
from common.tests.factories import device_factory


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class DeviceAttendanceSyncTaskTests(BaseTenantTestCase):
    @patch("attendance.services.device_attendance_pull")
    def test_sync_one_delegates_to_service(self, mock_pull):
        device_factory(serial_number="TEST001", company=self.tenant)
        mock_pull.return_value = {"created": 1}

        result = device_attendance_sync_task("TEST001")

        mock_pull.assert_called_once_with(serial_number="TEST001")
        self.assertEqual(result["created"], 1)

    @patch("attendance.tasks.device_attendance_sync_task.delay")
    def test_sync_all_enqueues_active_devices(self, mock_delay):
        device_factory(serial_number="TEST001", company=self.tenant)
        device_factory(serial_number="TEST002", company=self.tenant, is_active=False)

        device_attendance_sync_all_task()

        mock_delay.assert_called_once_with("TEST001")
