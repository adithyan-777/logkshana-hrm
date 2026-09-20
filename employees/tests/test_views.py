from uuid import uuid4

from django.urls import reverse
from django_tenants.test.client import TenantClient

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    department_factory,
    employee_factory,
    permission_factory,
    position_factory,
    role_factory,
)
from employees.forms import EmployeeForm
from employees.models import Department, Employee, Permission, Position, Role


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
                "mobile": "+97433555200",
                "password": "SecurePass123!",
                "is_active": True,
            }
        )

        self.assertTrue(form.is_valid())

    def test_requires_password_on_create(self):
        form = EmployeeForm(
            data={
                "first_name": "NoPassword",
                "last_name": "Employee",
                "emp_code": "E201",
                "mobile": "+97433555201",
                "is_active": True,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_mobile_is_optional(self):
        form = EmployeeForm(
            data={
                "first_name": "NoMobile",
                "last_name": "Employee",
                "emp_code": "E202",
                "password": "SecurePass123!",
                "is_active": True,
            }
        )

        self.assertTrue(form.is_valid())

    def test_rejects_common_password(self):
        form = EmployeeForm(
            data={
                "first_name": "Common",
                "last_name": "Password",
                "emp_code": "E203",
                "password": "password123",
                "is_active": True,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_rejects_numeric_password(self):
        form = EmployeeForm(
            data={
                "first_name": "Numeric",
                "last_name": "Password",
                "emp_code": "E204",
                "password": "9876543210",
                "is_active": True,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)


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
                "mobile": "+97433555222",
                "password": "SecurePass123!",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "employeeCreated")
        self.assertTemplateUsed(response, "employee_invite")
        self.assertContains(response, "/accounts/password/reset/key/")
        self.assertContains(response, 'data-invite-link="')
        self.assertNotContains(response, "onclick=")
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

    def test_list_shows_edit_link(self):
        employee = employee_factory(first_name="Editable", emp_code="E-EDT")

        response = self.client.get(reverse("employee_list"))

        self.assertContains(response, reverse("employee_edit", args=[employee.pk]))
        self.assertContains(response, "Edit")

    def test_edit_updates_employee(self):
        employee = employee_factory(first_name="Before", emp_code="E-UPD")
        department = department_factory(name="Ops", code="OPS")

        response = self.client.post(
            reverse("employee_edit", args=[employee.pk]),
            {
                "first_name": "After",
                "last_name": "Updated",
                "emp_code": "E-UPD",
                "department": department.pk,
                "email": "after@example.com",
                "mobile": "+97433555333",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "employeeUpdated")
        employee.refresh_from_db()
        self.assertEqual(employee.first_name, "After")
        self.assertEqual(employee.last_name, "Updated")
        self.assertEqual(employee.department, department)
        self.assertEqual(employee.email, "after@example.com")

    def test_edit_returns_404_for_missing_employee(self):
        response = self.client.get(reverse("employee_edit", args=[999999]))

        self.assertEqual(response.status_code, 404)


class DepartmentViewTests(BaseTenantTestCase):
    def test_list_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("department_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("department_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Departments")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            reverse("department_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "department_table")

    def test_list_shows_created_department(self):
        department_factory(name="Engineering", code="ENG")

        response = self.client.get(reverse("department_list"))

        self.assertContains(response, "Engineering")
        self.assertContains(response, "ENG")

    def test_list_pagination(self):
        for index in range(26):
            department_factory(name=f"Dept {index:02d}", code=f"D-{index:02d}")

        page_one = self.client.get(reverse("department_list"))
        page_two = self.client.get(reverse("department_list"), {"page": 2})

        self.assertContains(page_one, "Showing 1–25 of 26")
        self.assertContains(page_two, "Showing 26–26 of 26")

    def test_add_creates_department(self):
        response = self.client.post(
            reverse("department_add"),
            {"name": "Engineering", "code": "ENG"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "departmentCreated")
        self.assertTrue(Department.objects.filter(code="ENG").exists())

    def test_add_rejects_invalid_data(self):
        response = self.client.post(reverse("department_add"), {"name": ""})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Department.objects.filter(name="").exists())


class PositionViewTests(BaseTenantTestCase):
    def test_list_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("position_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("position_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Positions")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            reverse("position_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "position_table")

    def test_list_shows_created_position(self):
        position_factory(title="Manager", code="MGR")

        response = self.client.get(reverse("position_list"))

        self.assertContains(response, "Manager")
        self.assertContains(response, "MGR")

    def test_list_pagination(self):
        for index in range(26):
            position_factory(title=f"Title {index:02d}", code=f"P-{index:02d}")

        page_one = self.client.get(reverse("position_list"))
        page_two = self.client.get(reverse("position_list"), {"page": 2})

        self.assertContains(page_one, "Showing 1–25 of 26")
        self.assertContains(page_two, "Showing 26–26 of 26")

    def test_add_creates_position(self):
        response = self.client.post(
            reverse("position_add"),
            {"title": "Manager", "code": "MGR"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "positionCreated")
        self.assertTrue(Position.objects.filter(code="MGR").exists())


class RoleViewTests(BaseTenantTestCase):
    def test_list_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("role_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("role_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Roles")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            reverse("role_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "role_table")

    def test_list_shows_created_role(self):
        role_factory(name="Manager")

        response = self.client.get(reverse("role_list"))

        self.assertContains(response, "Manager")

    def test_list_pagination(self):
        for index in range(26):
            role_factory(name=f"Role-{index:02d}")

        page_one = self.client.get(reverse("role_list"))
        page_two = self.client.get(reverse("role_list"), {"page": 2})

        self.assertContains(page_one, "Showing 1–25 of 27")
        self.assertContains(page_two, "Showing 26–27 of 27")

    def test_add_creates_role(self):
        response = self.client.post(
            reverse("role_add"),
            {"name": "Manager"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "roleCreated")
        self.assertTrue(Role.objects.filter(name="Manager").exists())

    def test_add_attaches_permissions(self):
        view_perm = permission_factory(codename="view_employees", name="View")
        add_perm = permission_factory(codename="add_employees", name="Add")

        response = self.client.post(
            reverse("role_add"),
            {
                "name": "HR Manager",
                "permissions": [view_perm.pk, add_perm.pk],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "roleCreated")
        role = Role.objects.get(name="HR Manager")
        self.assertEqual(set(role.permissions.all()), {view_perm, add_perm})

    def test_add_form_seeds_catalog_as_checkboxes(self):
        response = self.client.get(reverse("role_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="permission-multiselect"')
        self.assertContains(response, 'type="checkbox"')
        self.assertContains(response, "Dashboard")
        self.assertContains(response, "Employees")
        self.assertContains(response, "View employees")
        self.assertNotContains(response, "employees.view")
        self.assertTrue(Permission.objects.filter(codename="employees.view").exists())


class PermissionViewTests(BaseTenantTestCase):
    def test_list_requires_login(self):
        client = TenantClient(self.tenant)
        response = client.get(reverse("permission_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_returns_200_when_authenticated(self):
        response = self.client.get(reverse("permission_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Permissions")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            reverse("permission_list"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "permission_table")

    def test_list_shows_created_permission(self):
        permission_factory(codename="view_employees", name="View Employees")

        response = self.client.get(reverse("permission_list"), {"q": "view_employees"})

        self.assertContains(response, "view_employees")
        self.assertContains(response, "View Employees")

    def test_list_pagination(self):
        self.client.get(reverse("permission_list"))
        existing = Permission.objects.count()
        for index in range(26):
            permission_factory(
                codename=f"perm_{index:02d}", name=f"Permission {index:02d}"
            )
        total = existing + 26
        last_page = (total // 25) + (1 if total % 25 else 0)
        last_start = (last_page - 1) * 25 + 1

        page_one = self.client.get(reverse("permission_list"))
        last = self.client.get(reverse("permission_list"), {"page": last_page})

        self.assertContains(page_one, f"Showing 1–25 of {total}")
        self.assertContains(last, f"Showing {last_start}–{total} of {total}")

    def test_add_creates_permission(self):
        response = self.client.post(
            reverse("permission_add"),
            {
                "codename": "view_employees",
                "name": "View Employees",
                "description": "Read-only access",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "permissionCreated")
        self.assertTrue(Permission.objects.filter(codename="view_employees").exists())
