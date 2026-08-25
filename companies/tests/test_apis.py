from django.urls import reverse
from django_tenants.test.client import TenantClient

from attendance.models import AttendanceTransaction
from common.tests.base import BaseTenantTestCase
from common.tests.factories import device_factory, employee_factory


class AttendanceLogCreateApiTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("attendance-log-create")

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
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["employee_id"], "E001")
        self.assertEqual(payload["serial_number"], "ZK-001")
        self.assertTrue(payload["external_id"].startswith("device:ZK-001:E001:"))
        self.assertEqual(AttendanceTransaction.objects.count(), 1)

    def test_rejects_missing_fields(self):
        client = TenantClient(self.tenant)

        response = client.post(
            self.url,
            {"serial_number": "ZK-001"},
            content_type="application/json",
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

        first = client.post(self.url, payload, content_type="application/json")
        second = client.post(self.url, payload, content_type="application/json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(AttendanceTransaction.objects.count(), 1)
