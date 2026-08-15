from uuid import uuid4

from django.urls import reverse
from django_tenants.test.client import TenantClient

from common.tests.base import BaseTenantTestCase
from common.tests.factories import department_factory, employee_factory
from employees.forms import EmployeeForm
from employees.models import Employee


class EmployeeFormTests(BaseTenantTestCase):
    def test_requires_first_name(self):
        form = EmployeeForm(data={"first_name": "", "last_name": "Doe"})

        self.assertFalse(form.is_valid())
        self.assertIn("first_name", form.errors)

    def test_accepts_valid_data_with_department(self):
        department = department_factory(name="HR", code="HR")

        form = EmployeeForm(
            data={
                "first_name": "Valid",
                "last_name": "Employee",
                "emp_code": "E200",
                "department": department.pk,
                "email": "valid@example.com",
                "is_active": True,
            }
        )

        self.assertTrue(form.is_valid())


class EmployeeViewTests(BaseTenantTestCase):
    def test_list_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("employee_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("employee_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Employees")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            reverse("employee_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "employee_table")

    def test_boosted_list_returns_full_page(self):
        response = self.client.get(
            reverse("employee_list"),
            HTTP_HX_REQUEST="true",
            HTTP_HX_BOOSTED="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "employees/list.html")
        self.assertContains(response, 'id="spa-view"')
        self.assertContains(response, "alpine-app.js")

    def test_add_creates_employee_and_returns_invite(self):
        emp_code = f"E-{uuid4().hex[:6]}"
        response = self.client.post(
            reverse("employee_add"),
            {
                "first_name": "New",
                "last_name": "Hire",
                "emp_code": emp_code,
                "email": "new.hire@example.com",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "employeeCreated")
        self.assertTemplateUsed(response, "employee_invite")
        self.assertContains(response, "/accounts/password/reset/key/")
        self.assertTrue(Employee.objects.filter(emp_code=emp_code).exists())

    def test_list_shows_created_employee(self):
        employee_factory(first_name="Visible", emp_code="E-VIS")

        response = self.client.get(reverse("employee_list"))

        self.assertContains(response, "Visible")
        self.assertContains(response, "E-VIS")

    def test_list_pagination(self):
        for index in range(26):
            employee_factory(
                first_name=f"Paginated{index:02d}",
                emp_code=f"E-PG-{index:02d}",
            )

        page_one = self.client.get(reverse("employee_list"))
        page_two = self.client.get(reverse("employee_list"), {"page": 2})
        htmx_page_one = self.client.get(
            reverse("employee_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(page_one, "Showing 1–25 of 26")
        self.assertContains(page_two, "Showing 26–26 of 26")
        self.assertContains(htmx_page_one, 'class="pagination"')
        self.assertEqual(page_one.content.count(b"<tr>"), 26)
        self.assertEqual(page_two.content.count(b"<tr>"), 2)
