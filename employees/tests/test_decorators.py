from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import reverse
from django_tenants.test.client import TenantClient, TenantRequestFactory

from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import employee_factory, permission_factory, role_factory
from employees.decorators import require_permission


@require_permission("test.protected")
def _protected_view(request):
    return HttpResponse("ok")


class RequirePermissionTests(BaseTenantTestCase):
    def _request(self, *, user):
        request = TenantRequestFactory(self.tenant).get("/protected/")
        request.user = user
        return request

    def _grant_permission(self):
        permission = permission_factory(codename="test.protected", name="Protected")
        role = role_factory(name="Protected Role", permissions=[permission])
        employee = employee_factory(first_name="HasPerm", emp_code="PERM-OK")
        employee.role = role
        employee.save(update_fields=["role"])
        return employee.user

    def test_anonymous_redirects_to_login(self):
        response = _protected_view(self._request(user=AnonymousUser()))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_authenticated_without_permission_denied(self):
        employee = employee_factory(first_name="Denied", emp_code="PERM-DN")
        with self.assertRaises(PermissionDenied):
            _protected_view(self._request(user=employee.user))

    def test_authenticated_with_permission_allows(self):
        user = self._grant_permission()

        response = _protected_view(self._request(user=user))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_admin_bypasses_without_role_permission(self):
        response = _protected_view(self._request(user=self.user))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_employee_list_forbidden_for_non_admin(self):
        employee = employee_factory(first_name="Limited", emp_code="PERM-403")
        user = employee.user
        user.set_password(TEST_PASSWORD)
        user.save()

        client = TenantClient(self.tenant)
        self.assertTrue(client.login(email=user.email, password=TEST_PASSWORD))
        response = client.get(reverse("employee_list"))

        self.assertEqual(response.status_code, 403)
