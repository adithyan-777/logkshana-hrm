from django.test import override_settings
from django.urls import reverse
from django_tenants.test.client import TenantClient

from attendance.models import AttendanceTransaction
from common.tests.base import BaseTenantTestCase
from common.tests.factories import device_factory, employee_factory

TEST_GATEWAY_SECRET = "test-gateway-secret"


class AttendanceLogCreateApiTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("attendance-log-create")
        # NOTE: class-level @override_settings does not take effect with
        # FastTenantTestCase (its setUpClass bypasses Django's class-override
        # hook), so enable the override here instead.
        self._gateway_override = override_settings(
            GATEWAY_SECRET_KEY=TEST_GATEWAY_SECRET
        )
        self._gateway_override.enable()
        self.addCleanup(self._gateway_override.disable)

    def gateway_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {TEST_GATEWAY_SECRET}"}

    def test_creates_punch_without_login(self):
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee_factory(first_name="Alice", emp_code="E001")
        client = TenantClient(self.tenant)

        response = client.post(
            self.url,
            {
                "serial_number": "ZK-001",
                "employee_id": "E001",
                "timestamp": "2026-08-25T08:01:00Z",
            },
            content_type="application/json",
            **self.gateway_headers(),
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["employee_id"], "E001")
        self.assertEqual(payload["serial_number"], "ZK-001")
        self.assertTrue(payload["external_id"].startswith("device:ZK-001:E001:"))
        self.assertEqual(AttendanceTransaction.objects.count(), 1)

    def test_accepts_gateway_native_payload(self):
        """Gateway pushes {id, serial_number, user_id, timestamp, ...}."""
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee_factory(first_name="Alice", emp_code="1001")
        client = TenantClient(self.tenant)

        response = client.post(
            self.url,
            {
                "id": 101,
                "serial_number": "ZK-001",
                "user_id": "1001",
                "timestamp": "2026-08-25T08:01:00Z",
                "status": 0,
                "verify_mode": 1,
                "work_code": "0",
            },
            content_type="application/json",
            **self.gateway_headers(),
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["employee_id"], "1001")
        self.assertEqual(AttendanceTransaction.objects.count(), 1)

    def test_gateway_log_id_keys_external_id(self):
        """gateway_log_id is optional; when present it keys the punch."""
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee_factory(first_name="Alice", emp_code="1001")
        client = TenantClient(self.tenant)

        response = client.post(
            self.url,
            {
                "gateway_id": "gateway-1",
                "gateway_log_id": 2,
                "serial_number": "ZK-001",
                "user_id": "1001",
                "timestamp": "2026-09-11T09:00:00+03:00",
                "status": 0,
                "verify_mode": 1,
                "work_code": "0",
            },
            content_type="application/json",
            **self.gateway_headers(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["external_id"], "gateway:2")
        punch = AttendanceTransaction.objects.get()
        self.assertEqual(punch.external_id, "gateway:2")
        self.assertEqual(punch.raw_data["gateway_id"], "gateway-1")
        self.assertEqual(punch.raw_data["gateway_log_id"], 2)

    def test_rejects_missing_auth(self):
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee_factory(first_name="Alice", emp_code="E001")
        client = TenantClient(self.tenant)

        response = client.post(
            self.url,
            {
                "serial_number": "ZK-001",
                "employee_id": "E001",
                "timestamp": "2026-08-25T08:01:00Z",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(AttendanceTransaction.objects.count(), 0)

    def test_rejects_wrong_auth(self):
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee_factory(first_name="Alice", emp_code="E001")
        client = TenantClient(self.tenant)

        response = client.post(
            self.url,
            {
                "serial_number": "ZK-001",
                "employee_id": "E001",
                "timestamp": "2026-08-25T08:01:00Z",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer wrong-secret",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(AttendanceTransaction.objects.count(), 0)

    def test_accepts_x_gateway_token_header(self):
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee_factory(first_name="Alice", emp_code="E001")
        client = TenantClient(self.tenant)

        response = client.post(
            self.url,
            {
                "serial_number": "ZK-001",
                "employee_id": "E001",
                "timestamp": "2026-08-25T08:01:00Z",
            },
            content_type="application/json",
            HTTP_X_GATEWAY_TOKEN=TEST_GATEWAY_SECRET,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(AttendanceTransaction.objects.count(), 1)

    def test_rejects_missing_fields(self):
        client = TenantClient(self.tenant)

        response = client.post(
            self.url,
            {"serial_number": "ZK-001"},
            content_type="application/json",
            **self.gateway_headers(),
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("employee_id", body)
        self.assertIn("timestamp", body)
        self.assertEqual(AttendanceTransaction.objects.count(), 0)

    def test_rejects_unknown_device(self):
        employee_factory(first_name="Alice", emp_code="E001")
        client = TenantClient(self.tenant)

        response = client.post(
            self.url,
            {
                "serial_number": "MISSING",
                "employee_id": "E001",
                "timestamp": "2026-08-25T08:01:00Z",
            },
            content_type="application/json",
            **self.gateway_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("serial_number", response.json())
        self.assertEqual(AttendanceTransaction.objects.count(), 0)

    def test_rejects_unknown_employee(self):
        device_factory(serial_number="ZK-001", company=self.tenant)
        client = TenantClient(self.tenant)

        response = client.post(
            self.url,
            {
                "serial_number": "ZK-001",
                "employee_id": "MISSING",
                "timestamp": "2026-08-25T08:01:00Z",
            },
            content_type="application/json",
            **self.gateway_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("employee_id", response.json())
        self.assertEqual(AttendanceTransaction.objects.count(), 0)

    def test_replay_is_idempotent(self):
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee_factory(first_name="Alice", emp_code="E001")
        client = TenantClient(self.tenant)
        payload = {
            "serial_number": "ZK-001",
            "employee_id": "E001",
            "timestamp": "2026-08-25T08:01:00Z",
        }

        first = client.post(
            self.url, payload, content_type="application/json", **self.gateway_headers()
        )
        second = client.post(
            self.url, payload, content_type="application/json", **self.gateway_headers()
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(AttendanceTransaction.objects.count(), 1)
