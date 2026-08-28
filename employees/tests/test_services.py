from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from common.tests.base import BaseTenantTestCase
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

    def test_generates_unique_username_for_same_name(self):
        first = employee_create(first_name="John", last_name="Smith", emp_code="E010")
        second = employee_create(first_name="John", last_name="Smith", emp_code="E011")

        self.assertNotEqual(first.user.username, second.user.username)
        self.assertTrue(first.user.username.startswith("johnsmith"))

    def test_employee_invite_link_contains_reset_path(self):
        employee = employee_factory(first_name="Invite", last_name="User", emp_code="E020")
        request = RequestFactory().get("/employees/add/")

        invite_link = employee_invite_link(employee=employee, request=request)

        self.assertTrue(invite_link.startswith("http://"))
        self.assertIn("/accounts/password/reset/key/", invite_link)


class EmployeeModelTests(BaseTenantTestCase):
    def test_soft_delete_excludes_from_default_manager(self):
        employee = employee_factory(first_name="Deleted", emp_code="E030")
        employee.delete()

        self.assertEqual(Employee.objects.count(), 0)
        self.assertEqual(Employee.all_objects.count(), 1)
