from datetime import date

from django.contrib.auth import get_user_model
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name, schema_context

from companies.models import Company

User = get_user_model()

TEST_PASSWORD = "password"


def _ensure_public_tenant():
    """Ensure the public tenant and a bootstrap owner user exist.

    The owner is created via direct save (not UserProfileManager.create_user,
    which itself requires the public tenant to already exist) to break the
    chicken-and-egg dependency between the public tenant and its owner.
    """
    public_schema = get_public_schema_name()
    public_tenant = Company.objects.filter(schema_name=public_schema).first()
    if public_tenant is not None:
        return public_tenant

    owner, created = User.objects.get_or_create(
        username="public_owner",
        defaults={"email": "public.owner@example.com"},
    )
    if created:
        owner.set_password(TEST_PASSWORD)
        owner.save(update_fields=["password"])

    public_tenant = Company(
        schema_name=public_schema,
        name="Public",
        paid_until=date(2099, 1, 1),
        on_trial=True,
        owner=owner,
    )
    public_tenant.auto_create_schema = False
    public_tenant.save()
    return public_tenant


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
        # TenantBase.owner is a required non-null FK. setup_tenant runs in the
        # public schema (before the test tenant is saved), so bootstrap the
        # public tenant + owner user first, then reuse that owner.
        with schema_context(get_public_schema_name()):
            public_tenant = _ensure_public_tenant()
            tenant.owner = public_tenant.owner

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        schema = cls.get_test_schema_name()
        with schema_context(get_public_schema_name()):
            _ensure_public_tenant()
            cls.user, created = User.objects.get_or_create(
                email=f"test_{schema}@example.com",
                defaults={"username": f"testuser_{schema}"},
            )
            if created:
                cls.user.set_password(TEST_PASSWORD)
                cls.user.save()
            elif not cls.user.username:
                cls.user.username = f"testuser_{schema}"
                cls.user.set_password(TEST_PASSWORD)
                cls.user.save()
            cls.user.tenants.add(cls.tenant)

        from tenant_users.permissions.models import UserTenantPermissions

        UserTenantPermissions.objects.update_or_create(
            profile=cls.user,
            defaults={"is_staff": True},
        )

    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
        self.client.login(email=self.user.email, password=TEST_PASSWORD)

    def login_as(self, *, user, via="email"):
        if via == "username":
            return self.client.login(username=user.username, password=TEST_PASSWORD)
        return self.client.login(email=user.email, password=TEST_PASSWORD)
