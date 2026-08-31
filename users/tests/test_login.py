from datetime import date

from django.urls import reverse
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name, schema_context

from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from companies.models import Company, Domain

OTHER_SCHEMA = "other_login_test"
OTHER_DOMAIN = "other.fast-test.com"


class TenantUserLoginTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.client.logout()

    def test_login_with_email_via_client(self):
        self.assertTrue(self.login_as(user=self.user, via="email"))

    def test_login_with_username_via_client(self):
        self.assertTrue(self.login_as(user=self.user, via="username"))

    def test_post_login_with_email(self):
        response = self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": TEST_PASSWORD},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))

    def test_post_login_with_username(self):
        response = self.client.post(
            reverse("account_login"),
            {"login": self.user.username, "password": TEST_PASSWORD},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))

    def test_post_login_wrong_password_stays_anonymous(self):
        response = self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_post_login_unknown_identifier_stays_anonymous(self):
        response = self.client.post(
            reverse("account_login"),
            {"login": "nobody@example.com", "password": TEST_PASSWORD},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_unauthenticated_request_reaches_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("account_login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email or username")


class TenantAccessTests(BaseTenantTestCase):
    def test_member_of_other_tenant_gets_404(self):
        with schema_context(get_public_schema_name()):
            existing = Company.objects.filter(schema_name=OTHER_SCHEMA).first()
            if existing is not None:
                existing.delete()
            other = Company(
                schema_name=OTHER_SCHEMA,
                name="Other Co",
                paid_until=date(2099, 1, 1),
                on_trial=True,
            )
            other.save()
            Domain.objects.create(
                domain=OTHER_DOMAIN,
                tenant=other,
                is_primary=True,
            )

        try:
            client = TenantClient(other)
            self.assertTrue(
                client.login(email=self.user.email, password=TEST_PASSWORD)
            )
            response = client.get(reverse("dashboard"))
            self.assertEqual(response.status_code, 404)
        finally:
            with schema_context(get_public_schema_name()):
                leftover = Company.objects.filter(schema_name=OTHER_SCHEMA).first()
                if leftover is not None:
                    leftover.delete()
