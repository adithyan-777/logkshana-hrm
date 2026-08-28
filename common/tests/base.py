from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from companies.models import Company

User = get_user_model()


class BaseTenantTestCase(TestCase):
    """Shared test setup that creates a company and a logged-in user."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Company.objects.create(
            name="Test Company",
            paid_until=date(2099, 1, 1),
            on_trial=True,
        )
        cls.user = User.objects.create_user(username="testuser", password="password")

    def setUp(self):
        self.client.login(username=self.user.username, password="password")
