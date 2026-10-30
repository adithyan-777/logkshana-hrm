import json
from types import SimpleNamespace

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from common.http import is_htmx_partial, redirect_to_list_drawer, set_hx_trigger
from common.views import select_options_view


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


class SelectOptionsGuardTests(SimpleTestCase):
    """Non-HTMX visits of the select-options fragment redirect out."""

    def setUp(self):
        self.factory = RequestFactory()
        self.url = reverse("select_options")

    def _request(self, referer=None, *, user=True):
        kwargs = {}
        if referer is not None:
            kwargs["HTTP_REFERER"] = referer
        request = self.factory.get(self.url, **kwargs)
        if user:
            request.user = SimpleNamespace(is_authenticated=True)
        return select_options_view(request)

    def test_referer_is_not_trusted_goes_to_reports(self):
        # Reload referers can be the tab's historical committed document —
        # an arbitrary old page (observed: the exceptions report). Never
        # follow it for aux option endpoints.
        response = self._request("http://testserver/reports/exceptions/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("report_hub"))

    def test_self_referential_referer_goes_to_reports(self):
        # Refreshing a previously pushed fragment URL sends /select-options/
        # back as its own Referer; redirecting to it would loop.
        response = self._request(
            "http://testserver/select-options/?source=employees&target=xfilt-employee"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("report_hub"))

    def test_missing_referer_goes_to_reports(self):
        response = self._request()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("report_hub"))

    def test_unauthenticated_goes_to_login(self):
        response = self._request("http://testserver/reports/individual/", user=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("account_login"))


class RedirectToListDrawerTests(SimpleTestCase):
    def test_builds_list_url_with_drawer_query(self):
        response = redirect_to_list_drawer(
            list_url_name="timetable_list",
            form_url="/schedule/timetables/1/edit/",
            title="Edit timetable",
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("timetable_list")))
        self.assertIn("drawer=", response.url)
        self.assertIn("drawer_title=Edit+timetable", response.url)
