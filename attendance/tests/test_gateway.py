import io
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from attendance.integrations.gateway import device_gateway_attendance_fetch


@override_settings(DEVICE_GATEWAY_BASE_URL="http://gw.test")
class DeviceGatewayAttendanceFetchURLTests(SimpleTestCase):
    def _urlopen_mock(self):
        mock = patch("attendance.integrations.gateway.urlopen")
        context = mock.start()
        self.addCleanup(mock.stop)
        context.return_value.__enter__.return_value = io.BytesIO(b"[]")
        return context

    def test_builds_per_device_pagination_url(self):
        run = self._urlopen_mock()
        device_gateway_attendance_fetch(serial_number="AJE001")

        request = run.call_args[0][0]
        self.assertEqual(
            request.full_url,
            "http://gw.test/api/devices/AJE001/attendance",
        )

    def test_after_id_goes_in_the_query(self):
        run = self._urlopen_mock()
        device_gateway_attendance_fetch(
            serial_number="AJE001", after_id=7
        )

        request = run.call_args[0][0]
        self.assertEqual(
            request.full_url,
            "http://gw.test/api/devices/AJE001/attendance?after_id=7",
        )
