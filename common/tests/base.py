from datetime import date

from django.contrib.auth import get_user_model
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name, schema_context

User = get_user_model()


class BaseTenantTestCase(FastTenantTestCase):
    """
    Shared tenant test setup for TENANT_APPS (employees, schedule, leave).

    Uses FastTenantTestCase so the tenant schema is created once per test class.
    See: https://django-tenants.readthedocs.io/en/latest/test.html
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test Company"
        tenant.paid_until = date(2099, 1, 1)
        tenant.on_trial = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with schema_context(get_public_schema_name()):
            username = f"testuser_{cls.get_test_schema_name()}"
            cls.user, created = User.objects.get_or_create(username=username)
            if created:
                cls.user.set_password("password")
                cls.user.save()

    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
        self.client.login(username=self.user.username, password="password")
