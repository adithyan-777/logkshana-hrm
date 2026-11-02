from django.http import HttpRequest
from django.test import SimpleTestCase
from django.urls import reverse
from django_tenants.utils import get_public_schema_name

from common.feature_flags import Feature, feature_hidden, features_hidden
from common.tests.base import BaseTenantTestCase
from companies.models import Company
from config.context_processors import navigation


def set_hidden(tenant, features: list[str]) -> None:
    """Set the tenant's hidden feature keys, refreshing the cached row.

    FastTenantTestCase shares one DB per class without per-test
    rollback: every test establishes its own flag state first.
    """
    Company.objects.filter(pk=tenant.pk).update(hidden_features=features)
    tenant.refresh_from_db()


class FeatureHelperTests(SimpleTestCase):
    def test_missing_attribute_fails_open(self):
        self.assertEqual(features_hidden(None), [])
        self.assertEqual(features_hidden(object()), [])

    def test_non_list_values_fail_open(self):
        dict_stub = type("T", (), {"hidden_features": {Feature.LEAVE: True}})()
        self.assertEqual(features_hidden(dict_stub), [])
        string_stub = type("T", (), {"hidden_features": "leave"})()
        self.assertEqual(features_hidden(string_stub), [])
        none_stub = type("T", (), {"hidden_features": None})()
        self.assertEqual(features_hidden(none_stub), [])

    def test_non_string_keys_ignored(self):
        mixed = type("T", (), {"hidden_features": [123, None, Feature.LEAVE]})()
        self.assertEqual(features_hidden(mixed), [Feature.LEAVE])

    def test_feature_hidden_matches_listed_keys(self):
        stub = type("T", (), {"hidden_features": [Feature.LEAVE]})()
        self.assertTrue(feature_hidden(stub, Feature.LEAVE))
        self.assertFalse(feature_hidden(stub, "employees"))
        empty = type("T", (), {"hidden_features": []})()
        self.assertFalse(feature_hidden(empty, Feature.LEAVE))


class LeaveFeatureNavTests(BaseTenantTestCase):
    """Per-tenant `leave` feature flag hides the Leave nav + alerts.

    The sidebar, dashboard, notifications menu, and command palette all
    key off `nav_can.leave` / `nav_alerts.pending_leave`, both produced
    by config.context_processors.navigation — so the processor is the
    test surface.
    """

    @staticmethod
    def _request(tenant, user) -> HttpRequest:
        request = HttpRequest()
        request.path = "/dashboard/"
        request.resolver_match = type("Match", (), {"url_name": "dashboard"})()
        request.tenant = tenant  # type: ignore[attr-defined]
        request.user = user  # type: ignore[attr-defined]
        return request

    def _set_hidden(self, features: list[str]) -> None:
        set_hidden(self.tenant, features)

    def test_nav_visible_by_default(self):
        self._set_hidden([])
        context = navigation(self._request(self.tenant, self.user))
        self.assertTrue(context["nav_can"]["leave"])

    def test_hidden_feature_hides_nav_and_alert_and_palette(self):
        self._set_hidden([Feature.LEAVE])
        context = navigation(self._request(self.tenant, self.user))
        self.assertFalse(context["nav_can"]["leave"])
        self.assertEqual(context["nav_alerts"]["pending_leave"], 0)
        palette_urls = {i["url_name"] for i in context["command_palette"]}
        leave_urls = {
            "leave_request_list",
            "leave_request_add",
            "leave_type_list",
            "leave_policy_list",
            "holiday_list",
            "report_leave",
        }
        self.assertFalse(palette_urls & leave_urls)

    def test_other_features_untouched(self):
        self._set_hidden([Feature.LEAVE])
        context = navigation(self._request(self.tenant, self.user))
        self.assertTrue(context["nav_can"]["employees"])
        self.assertTrue(context["nav_can"]["reports"])
        self.assertIn("employee_list", [
            i["url_name"] for i in context["command_palette"]
        ])

    def test_schedule_flag_hides_only_schedule(self):
        self._set_hidden([Feature.SCHEDULE])
        context = navigation(self._request(self.tenant, self.user))
        self.assertFalse(context["nav_can"]["schedule"])
        self.assertTrue(context["nav_can"]["leave"])
        palette_urls = {i["url_name"] for i in context["command_palette"]}
        schedule_urls = {
            "timetable_list",
            "schedule_list",
            "assignment_add",
            "assignment_list",
            "employee_schedule_list",
        }
        self.assertFalse(palette_urls & schedule_urls)

    def test_public_schema_branch_never_hides(self):
        # The public schema has no tenant feature toggles: the public
        # branch must keep its default nav (fail-open).
        public_tenant = type(
            "PublicTenantStub", (), {"schema_name": get_public_schema_name()}
        )()
        user = type("AnonymousStub", (), {"is_authenticated": False})()
        context = navigation(self._request(public_tenant, user))
        self.assertTrue(context["nav_can"]["leave"])


class LeaveFeatureUrlTests(BaseTenantTestCase):
    """Hidden feature = 404 at the URL level, plus gated page markup."""

    def _hide_leave(self):
        set_hidden(self.tenant, [Feature.LEAVE])

    def test_leave_pages_reachable_by_default(self):
        set_hidden(self.tenant, [])
        for url_name in ("leave_type_list", "leave_request_list", "report_leave"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_leave_pages_404_when_hidden(self):
        self._hide_leave()
        for url_name in (
            "leave_type_list",
            "leave_type_add",
            "leave_type_edit",
            "leave_type_delete",
            "leave_policy_list",
            "leave_request_list",
            "leave_request_add",
            "holiday_list",
            "report_leave",
        ):
            with self.subTest(url_name=url_name):
                if url_name in ("leave_type_edit", "leave_type_delete"):
                    url = reverse(url_name, kwargs={"leave_type_id": 1})
                else:
                    url = reverse(url_name)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)

    def test_schedule_pages_404_when_hidden(self):
        set_hidden(self.tenant, [Feature.SCHEDULE])
        for url_name in ("timetable_list", "schedule_list", "assignment_list"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 404)

    def test_dashboard_drops_leave_markup_when_hidden(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "On leave")
        self.assertContains(response, reverse("leave_request_list"))

        self._hide_leave()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        # Metric link + "Needs attention" row + quick action are gone.
        self.assertNotContains(response, reverse("leave_request_list"))
        self.assertNotContains(response, "Awaiting approval")
