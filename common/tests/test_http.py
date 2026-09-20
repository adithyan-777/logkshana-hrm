import json

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from common.http import is_htmx_partial, set_hx_trigger


class IsHtmxPartialTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_plain_request_is_not_partial(self):
        request = self.factory.get("/")

        self.assertFalse(is_htmx_partial(request))

    def test_htmx_fragment_request_is_partial(self):
        request = self.factory.get("/", HTTP_HX_REQUEST="true")

        self.assertTrue(is_htmx_partial(request))

    def test_boosted_navigation_is_not_partial(self):
        request = self.factory.get(
            "/",
            HTTP_HX_REQUEST="true",
            HTTP_HX_BOOSTED="true",
        )

        self.assertFalse(is_htmx_partial(request))

    def test_history_restore_is_not_partial(self):
        request = self.factory.get(
            "/",
            HTTP_HX_REQUEST="true",
            HTTP_HX_HISTORY_RESTORE_REQUEST="true",
        )

        self.assertFalse(is_htmx_partial(request))


class SetHxTriggerTests(SimpleTestCase):
    def test_create_success_closes_modal_and_toasts(self):
        response = HttpResponse("ok")

        set_hx_trigger(
            response,
            event="departmentCreated",
            toast="Department created.",
        )

        payload = json.loads(response["HX-Trigger"])
        self.assertTrue(payload["departmentCreated"])
        self.assertTrue(payload["closeModal"])
        self.assertEqual(
            payload["showToast"],
            {"message": "Department created.", "type": "success"},
        )

    def test_employee_invite_keeps_drawer_open(self):
        response = HttpResponse("invite")

        set_hx_trigger(
            response,
            event="employeeCreated",
            toast="Employee added.",
            close_modal=False,
        )

        payload = json.loads(response["HX-Trigger"])
        self.assertTrue(payload["employeeCreated"])
        self.assertNotIn("closeModal", payload)
        self.assertEqual(payload["showToast"]["message"], "Employee added.")
