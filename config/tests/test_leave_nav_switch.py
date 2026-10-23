from django.http import HttpRequest
from django_tenants.utils import get_public_schema_name
from waffle.models import Switch

from common.tests.base import BaseTenantTestCase
from config.context_processors import navigation


class LeaveNavSwitchTests(BaseTenantTestCase):
    """Per-tenant `hide_leave` waffle switch hides the Leave nav + alerts.

    The sidebar, reports hub, and the notifications menu all key off
    `nav_can.leave` / `nav_alerts.pending_leave`, both produced by
    config.context_processors.navigation — so the processor is the test
    surface.
    """

    @staticmethod
    def _request(tenant, user) -> HttpRequest:
        request = HttpRequest()
        request.path = "/dashboard/"
        request.resolver_match = type("Match", (), {"url_name": "dashboard"})()
        request.tenant = tenant  # type: ignore[attr-defined]
        request.user = user  # type: ignore[attr-defined]
        return request

    def test_nav_visible_by_default(self):
        context = navigation(self._request(self.tenant, self.user))
        self.assertTrue(context["nav_can"]["leave"])

    def test_switch_row_off_keeps_nav_visible(self):
        Switch.objects.create(name="hide_leave", active=False)
        context = navigation(self._request(self.tenant, self.user))
        self.assertTrue(context["nav_can"]["leave"])

    def test_switch_row_on_hides_nav_and_alert(self):
        Switch.objects.create(name="hide_leave", active=True)
        context = navigation(self._request(self.tenant, self.user))
        self.assertFalse(context["nav_can"]["leave"])
        self.assertEqual(context["nav_alerts"]["pending_leave"], 0)

    def test_public_schema_branch_never_touches_waffle(self):
        # Public schema has no waffle tables (app is TENANT-only): the
        # public branch must keep its default nav without querying them.
        public_tenant = type(
            "PublicTenantStub", (), {"schema_name": get_public_schema_name()}
        )()
        user = type("AnonymousStub", (), {"is_authenticated": False})()
        context = navigation(self._request(public_tenant, user))
        self.assertTrue(context["nav_can"]["leave"])
