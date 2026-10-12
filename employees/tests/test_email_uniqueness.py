"""Email uniqueness: users (global) and employees (per tenant).

Blanks ("") mean "no email" and are exempt on both models. Everything
else must be unique case-insensitively.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from common.tests.base import BaseTenantTestCase
from common.tests.factories import employee_factory
from employees.services import employee_update
from users.admin import UserAdminChangeForm, UserAdminCreationForm

User = get_user_model()


class UserEmailUniquenessTests(BaseTenantTestCase):
    def test_duplicate_user_email_rejected_case_insensitively(self):
        employee_factory(first_name="Ana", emp_code="UE001", email="ana@example.com")

        with self.assertRaises(ValidationError) as ctx:
            employee_factory(first_name="Bob", emp_code="UE002", email="ANA@example.com")
        self.assertIn("email", ctx.exception.error_dict)

    def test_blank_user_emails_allowed_repeatedly(self):
        first = employee_factory(first_name="NoMail", emp_code="UE003", email="")
        second = employee_factory(first_name="NoMail2", emp_code="UE004", email="")

        self.assertEqual(first.email, "")
        self.assertEqual(second.email, "")
        self.assertNotEqual(first.user.email, second.user.email)

    def test_email_stored_normalized(self):
        employee = employee_factory(
            first_name="Case", emp_code="UE005", email="  MiXeD@Example.COM "
        )

        self.assertEqual(employee.email, "mixed@example.com")
        self.assertEqual(employee.user.email, "mixed@example.com")

    def test_db_constraint_backstop(self):
        User.objects.create_user(username="db1", email="taken@example.com")

        with self.assertRaises(IntegrityError):
            User.objects.create_user(username="db2", email="TAKEN@example.com")

    def test_db_constraint_ignores_blanks(self):
        User.objects.create_user(username="blank1", email="")
        User.objects.create_user(username="blank2", email="")


class EmployeeEmailUniquenessTests(BaseTenantTestCase):
    def test_duplicate_employee_email_rejected(self):
        employee_factory(first_name="Cara", emp_code="EE001", email="cara@example.com")

        with self.assertRaises(ValidationError) as ctx:
            employee_factory(first_name="Dan", emp_code="EE002", email="cara@example.com")
        self.assertIn("email", ctx.exception.error_dict)

    def test_update_to_anothers_email_rejected(self):
        employee_factory(first_name="Erin", emp_code="EE003", email="erin@example.com")
        bob = employee_factory(first_name="Bob", emp_code="EE004", email="bob@example.com")

        with self.assertRaises(ValidationError) as ctx:
            employee_update(employee=bob, first_name="Bob", email="ERIN@example.com")
        self.assertIn("email", ctx.exception.error_dict)

    def test_update_keeping_own_email_accepted(self):
        bob = employee_factory(first_name="Bob", emp_code="EE005", email="bob@example.com")

        updated = employee_update(
            employee=bob, first_name="Bobby", email="BOB@example.com"
        )

        self.assertEqual(updated.first_name, "Bobby")
        self.assertEqual(updated.email, "bob@example.com")

    def test_blank_employee_emails_allowed_repeatedly(self):
        employee_factory(first_name="E1", emp_code="EE006", email="")
        employee_factory(first_name="E2", emp_code="EE007", email="")


class UserAdminEmailTests(BaseTenantTestCase):
    def _form_data(self, **overrides):
        data = {
            "username": "formuser",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
            "email": "form@example.com",
        }
        data.update(overrides)
        return data

    def test_creation_form_rejects_duplicate_email(self):
        User.objects.create_user(username="existing", email="form@example.com")

        form = UserAdminCreationForm(data=self._form_data())

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_creation_form_accepts_blank_email(self):
        User.objects.create_user(username="blank-admin", email="")

        form = UserAdminCreationForm(data=self._form_data(email=""))

        self.assertTrue(form.is_valid())

    def test_change_form_rejects_anothers_email(self):
        User.objects.create_user(username="other", email="other@example.com")
        me = User.objects.create_user(username="me", email="me@example.com")

        form = UserAdminChangeForm(
            data={"username": "me", "email": "OTHER@example.com"}, instance=me
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
