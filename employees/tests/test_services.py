from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from django_tenants.test.client import TenantClient, TenantRequestFactory

from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import (
    department_factory,
    employee_factory,
    position_factory,
)
from employees.models import Employee
from employees.services import employee_create, employee_invite_link

User = get_user_model()


class EmployeeCreateTests(BaseTenantTestCase):
    def test_creates_employee_with_user(self):
        department = department_factory(name="Engineering", code="ENG")
        position = position_factory(title="Developer", code="DEV")

        employee = employee_create(
            first_name="Jane",
            last_name="Doe",
            emp_code="E001",
            department=department,
            position=position,
            email="jane@example.com",
            hire_date=date(2026, 1, 15),
        )

        self.assertEqual(employee.first_name, "Jane")
        self.assertEqual(employee.full_name, "Jane Doe")
        self.assertEqual(employee.department, department)
        self.assertEqual(employee.position, position)
        self.assertIsNotNone(employee.user)
        self.assertFalse(employee.user.has_usable_password())
        self.assertEqual(employee.user.username, "janedoe")
        self.assertEqual(employee.user.email, "jane@example.com")

    def test_generates_unique_username_for_same_name(self):
        first = employee_create(first_name="John", last_name="Smith", emp_code="E010")
        second = employee_create(first_name="John", last_name="Smith", emp_code="E011")

        self.assertNotEqual(first.user.username, second.user.username)
        self.assertTrue(first.user.username.startswith("johnsmith"))

    def test_same_name_with_emails_still_unique_usernames(self):
        first = employee_create(
            first_name="John",
            last_name="Smith",
            emp_code="E012",
            email="js1@example.com",
        )
        second = employee_create(
            first_name="John",
            last_name="Smith",
            emp_code="E013",
            email="js2@example.com",
        )

        self.assertNotEqual(first.user.username, second.user.username)
        self.assertTrue(first.user.username.startswith("johnsmith"))
        self.assertEqual(first.user.email, "js1@example.com")
        self.assertEqual(second.user.email, "js2@example.com")

    def test_employee_invite_link_contains_reset_path(self):
        employee = employee_factory(
            first_name="Invite", last_name="User", emp_code="E020"
        )
        request = TenantRequestFactory(self.tenant).get("/employees/add/")

        invite_link = employee_invite_link(employee=employee, request=request)

        self.assertTrue(invite_link.startswith("http://"))
        self.assertIn("/accounts/password/reset/key/", invite_link)

    def test_user_is_linked_to_current_tenant(self):
        employee = employee_create(
            first_name="Tenant",
            last_name="Member",
            emp_code="E040",
            email="tenant.member@example.com",
        )

        self.assertIn(self.tenant, employee.user.tenants.all())

    def test_created_user_can_login_to_tenant(self):
        employee = employee_create(
            first_name="Login",
            last_name="Worker",
            emp_code="E041",
            email="login.worker@example.com",
        )
        user = employee.user
        user.set_password(TEST_PASSWORD)
        user.save(update_fields=["password"])

        client = TenantClient(self.tenant)
        response = client.post(
            reverse("account_login"),
            {"login": user.email, "password": TEST_PASSWORD},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))
        self.assertTrue(client.login(email=user.email, password=TEST_PASSWORD))


class EmployeeModelTests(BaseTenantTestCase):
    def test_soft_delete_excludes_from_default_manager(self):
        employee = employee_factory(first_name="Deleted", emp_code="E030")
        employee.delete()

        self.assertEqual(Employee.objects.count(), 0)
        self.assertEqual(Employee.all_objects.count(), 1)
