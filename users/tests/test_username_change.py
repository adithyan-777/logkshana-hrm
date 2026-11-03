"""Self-service username change on the profile page."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from django_tenants.test.client import TenantClient

from common.tests.base import TEST_PASSWORD, BaseTenantTestCase

User = get_user_model()


class UsernameChangeTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        # Go back to the DB state from setUpClass: earlier tests in this
        # class may have renamed the shared test user in memory.
        self.user.refresh_from_db()
        self.url = reverse("account_profile")

    def _post(self, **overrides):
        data = {
            "username": self.user.username,
            "current_password": TEST_PASSWORD,
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_get_renders_username_form(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="current_password"')
        self.assertContains(response, self.user.username)

    def test_change_username_succeeds_and_new_username_logs_in(self):
        old_username = self.user.username

        response = self.client.post(
            self.url,
            {"username": "renamed.user", "current_password": TEST_PASSWORD},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username updated.")
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.username, old_username)
        self.assertEqual(self.user.username, "renamed.user")

        self.client.logout()
        self.assertTrue(self.login_as(user=self.user, via="username"))

    def test_duplicate_username_rejected_case_insensitively(self):
        User.objects.create_user(username="TakenUser", email="taken@example.com")
        original = self.user.username

        response = self._post(username="takenuser")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This username is already in use.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, original)

    def test_keeping_own_username_accepted(self):
        response = self.client.post(
            self.url,
            {"username": self.user.username, "current_password": TEST_PASSWORD},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username updated.")

    def test_wrong_current_password_rejected(self):
        original = self.user.username

        response = self._post(username="another.name", current_password="wrong-pass")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter your current password correctly.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, original)

    def test_empty_current_password_rejected(self):
        response = self._post(current_password="")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter your current password correctly.")

    def test_invalid_characters_rejected(self):
        response = self._post(username="bad name")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid username")

    def test_unauthenticated_post_redirects_to_login(self):
        client = TenantClient(self.tenant)

        response = client.post(
            self.url,
            {"username": "nobody", "current_password": TEST_PASSWORD},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response.url)
