import json

from django.test import override_settings
from django.urls import reverse
from django_tenants.test.client import TenantClient

from attendance.models import AttendanceTransaction
from common.tests.base import BaseTenantTestCase
from common.tests.factories import device_factory, employee_factory

TEST_GATEWAY_SECRET = "test-gateway-secret"


class GatewayViewTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("gateway")
        # NOTE: class-level @override_settings does not take effect with
        # FastTenantTestCase (its setUpClass bypasses Django's class-override
        # hook), so enable the override here instead.
        self._gateway_override = override_settings(
            GATEWAY_SECRET_KEY=TEST_GATEWAY_SECRET
        )
        self._gateway_override.enable()
        self.addCleanup(self._gateway_override.disable)
        device_factory(serial_number="ZK-001", company=self.tenant)
        employee_factory(first_name="Alice", emp_code="1001")

    def post_gateway(self, payload, **headers):
        client = TenantClient(self.tenant)
        default = {"HTTP_AUTHORIZATION": f"Bearer {TEST_GATEWAY_SECRET}"}
        default.update(headers)
        if isinstance(payload, (dict, list)):
            return client.post(
                self.url,
                json.dumps(payload),
                content_type="application/json",
                **default,
            )
        # Raw body (e.g. invalid JSON test).
        return client.post(
            self.url, payload, content_type="application/json", **default
        )

    def gateway_payload(self, **overrides):
        payload = {
            "id": 101,
            "serial_number": "ZK-001",
            "user_id": "1001",
            "timestamp": "2026-09-02T09:00:00Z",
            "status": 0,
            "verify_mode": 1,
            "work_code": "0",
        }
        payload.update(overrides)
        return payload

    def test_rejects_missing_auth(self):
        client = TenantClient(self.tenant)
        response = client.post(
            self.url,
            json.dumps(self.gateway_payload()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AttendanceTransaction.objects.count(), 0)

    def test_rejects_wrong_auth(self):
        response = self.post_gateway(
            self.gateway_payload(), HTTP_AUTHORIZATION="Bearer wrong-secret"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AttendanceTransaction.objects.count(), 0)

    def test_accepts_x_gateway_token_header(self):
        client = TenantClient(self.tenant)
        response = client.post(
            self.url,
            json.dumps(self.gateway_payload()),
            content_type="application/json",
            HTTP_X_GATEWAY_TOKEN=TEST_GATEWAY_SECRET,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AttendanceTransaction.objects.count(), 1)

    def test_accepts_legacy_secret_key_param(self):
        client = TenantClient(self.tenant)
        response = client.post(
            f"{self.url}?secret_key=test-gateway-secret",
            json.dumps(self.gateway_payload()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AttendanceTransaction.objects.count(), 1)

    def test_single_push_creates_punch_with_gateway_extras(self):
        response = self.post_gateway(self.gateway_payload())

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["employee_id"], "1001")
        self.assertEqual(body["serial_number"], "ZK-001")
        self.assertIn("id", body)

        punch = AttendanceTransaction.objects.get()
        self.assertEqual(punch.external_employee_id, "1001")
        self.assertEqual(punch.raw_data["verify_mode"], 1)
        self.assertEqual(punch.raw_data["work_code"], "0")
        self.assertEqual(punch.raw_data["id"], 101)

    def test_single_push_with_gateway_log_id(self):
        """Exact shape the real gateway sends (gateway_log_id, not id)."""
        response = self.post_gateway(
            {
                "gateway_id": "gateway-1",
                "gateway_log_id": 2,
                "serial_number": "ZK-001",
                "user_id": "1001",
                "timestamp": "2026-09-11T09:00:00+03:00",
                "status": 0,
                "verify_mode": 1,
                "work_code": "0",
                "some_future_field": "preserved-as-is",
            }
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["external_id"], "gateway:2")
        punch = AttendanceTransaction.objects.get()
        self.assertEqual(punch.external_id, "gateway:2")
        self.assertEqual(punch.external_employee_id, "1001")
        self.assertEqual(punch.raw_data["gateway_id"], "gateway-1")
        self.assertEqual(punch.raw_data["gateway_log_id"], 2)
        self.assertEqual(punch.raw_data["verify_mode"], 1)
        self.assertEqual(punch.raw_data["some_future_field"], "preserved-as-is")

    def test_single_push_accepts_employee_id_alias(self):
        payload = self.gateway_payload()
        del payload["user_id"]
        payload["employee_id"] = "1001"

        response = self.post_gateway(payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(AttendanceTransaction.objects.count(), 1)

    def test_single_push_missing_user_id_is_400(self):
        payload = self.gateway_payload()
        del payload["user_id"]

        response = self.post_gateway(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AttendanceTransaction.objects.count(), 0)

    def test_single_push_unknown_employee_is_400(self):
        response = self.post_gateway(self.gateway_payload(user_id="MISSING"))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AttendanceTransaction.objects.count(), 0)

    def test_single_push_replay_is_idempotent(self):
        first = self.post_gateway(self.gateway_payload())
        second = self.post_gateway(self.gateway_payload())

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(AttendanceTransaction.objects.count(), 1)

    def test_batch_push_creates_all(self):
        payload = [
            self.gateway_payload(id=101, timestamp="2026-09-02T09:00:00Z"),
            self.gateway_payload(id=102, timestamp="2026-09-02T17:30:00Z"),
        ]

        response = self.post_gateway(payload)

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["created"], 2)
        self.assertEqual(body["errors"], 0)
        self.assertEqual(AttendanceTransaction.objects.count(), 2)

    def test_batch_push_partial_failure_is_207(self):
        payload = [
            self.gateway_payload(id=101, timestamp="2026-09-02T09:00:00Z"),
            self.gateway_payload(id=102, user_id="MISSING"),
        ]

        response = self.post_gateway(payload)

        self.assertEqual(response.status_code, 207)
        body = response.json()
        self.assertEqual(body["created"], 1)
        self.assertEqual(body["errors"], 1)
        self.assertEqual(AttendanceTransaction.objects.count(), 1)

    def test_invalid_json_is_400(self):
        response = self.post_gateway("{not-json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AttendanceTransaction.objects.count(), 0)

    def test_get_is_not_allowed(self):
        client = TenantClient(self.tenant)
        response = client.get(
            self.url, HTTP_AUTHORIZATION=f"Bearer {TEST_GATEWAY_SECRET}"
        )
        self.assertEqual(response.status_code, 405)
