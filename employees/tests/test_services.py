from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse
from django_tenants.test.client import TenantClient, TenantRequestFactory

from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import (
    department_factory,
    employee_factory,
    permission_factory,
    position_factory,
)
from employees.models import Department, Employee, Permission, Position, Role
from employees.services import (
    department_create,
    employee_create,
    employee_invite_link,
    employee_role_ensure,
    employee_update,
    employees_assign_employee_role,
    permission_catalog_ensure,
    permission_create,
    position_create,
    role_create,
)

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
            mobile="+97433555001",
            hire_date=date(2026, 1, 15),
            password="SecurePass123!",
        )

        self.assertEqual(employee.first_name, "Jane")
        self.assertEqual(employee.full_name, "Jane Doe")
        self.assertEqual(employee.department, department)
        self.assertEqual(employee.position, position)
        self.assertIsNotNone(employee.user)
        self.assertTrue(employee.user.has_usable_password())
        self.assertTrue(employee.user.check_password("SecurePass123!"))
        self.assertFalse(employee.user.check_password("+97433555001"))
        self.assertEqual(employee.user.username, "janedoe")
        self.assertEqual(employee.user.email, "jane@example.com")
        self.assertEqual(employee.role.name, "Employee")
        self.assertEqual(
            list(employee.role.permissions.values_list("codename", flat=True)),
            ["attendance.own.view"],
        )

    def test_generates_unique_username_for_same_name(self):
        first = employee_create(
            first_name="John",
            last_name="Smith",
            emp_code="E010",
            mobile="+97433555010",
        )
        second = employee_create(
            first_name="John",
            last_name="Smith",
            emp_code="E011",
            mobile="+97433555011",
        )

        self.assertNotEqual(first.user.username, second.user.username)
        self.assertTrue(first.user.username.startswith("johnsmith"))

    def test_same_name_with_emails_still_unique_usernames(self):
        first = employee_create(
            first_name="John",
            last_name="Smith",
            emp_code="E012",
            email="js1@example.com",
            mobile="+97433555012",
        )
        second = employee_create(
            first_name="John",
            last_name="Smith",
            emp_code="E013",
            email="js2@example.com",
            mobile="+97433555013",
        )

        self.assertNotEqual(first.user.username, second.user.username)
        self.assertTrue(first.user.username.startswith("johnsmith"))
        self.assertEqual(first.user.email, "js1@example.com")
        self.assertEqual(second.user.email, "js2@example.com")

    def test_update_changes_employee_fields(self):
        employee = employee_create(
            first_name="Original",
            last_name="Name",
            emp_code="E050",
            email="original@example.com",
            mobile="+97433555050",
        )

        updated = employee_update(
            employee=employee,
            first_name="Changed",
            last_name="Person",
            emp_code="E050",
            email="changed@example.com",
            mobile="+97433555050",
            is_active=False,
        )

        self.assertEqual(updated.first_name, "Changed")
        self.assertEqual(updated.last_name, "Person")
        self.assertEqual(updated.email, "changed@example.com")
        self.assertFalse(updated.is_active)
        updated.user.refresh_from_db()
        self.assertEqual(updated.user.email, "changed@example.com")
        self.assertFalse(updated.user.is_active)

    def test_employee_invite_link_contains_reset_path(self):
        employee = employee_factory(
            first_name="Invite", last_name="User", emp_code="E020"
        )
        request = TenantRequestFactory(self.tenant).get("/employees/add/")

        invite_link = employee_invite_link(employee=employee, request=request)

        self.assertTrue(invite_link.startswith("http://"))
        self.assertIn("/accounts/password/reset/key/", invite_link)

    def test_mobile_is_optional(self):
        employee = employee_create(
            first_name="No",
            last_name="Phone",
            emp_code="E061",
            password="SecurePass123!",
        )

        self.assertEqual(employee.mobile, "")
        self.assertTrue(employee.user.check_password("SecurePass123!"))

    def test_short_password_raises(self):
        with self.assertRaises(ValidationError):
            employee_create(
                first_name="Short",
                last_name="Password",
                emp_code="E062",
                password="short",
            )

    def test_update_password_changes_login(self):
        employee = employee_create(
            first_name="Pw",
            last_name="Change",
            emp_code="E063",
            password="OldPass123!",
        )

        employee_update(
            employee=employee,
            first_name="Pw",
            last_name="Change",
            emp_code="E063",
            mobile=employee.mobile,
            password="NewPass456!",
        )

        employee.user.refresh_from_db()
        self.assertTrue(employee.user.check_password("NewPass456!"))
        self.assertFalse(employee.user.check_password("OldPass123!"))

    def test_user_is_linked_to_current_tenant(self):
        employee = employee_create(
            first_name="Tenant",
            last_name="Member",
            emp_code="E040",
            email="tenant.member@example.com",
            mobile="+97433555040",
        )

        self.assertIn(self.tenant, employee.user.tenants.all())

    def test_created_user_can_login_to_tenant(self):
        employee = employee_create(
            first_name="Login",
            last_name="Worker",
            emp_code="E041",
            email="login.worker@example.com",
            mobile="+97433555041",
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


class DepartmentCreateTests(BaseTenantTestCase):
    def test_creates_department(self):
        department = department_create(name="Engineering", code="ENG")

        self.assertEqual(department.name, "Engineering")
        self.assertEqual(department.code, "ENG")
        self.assertTrue(Department.objects.filter(code="ENG").exists())

    def test_supports_nested_departments(self):
        parent = department_factory(name="Engineering", code="ENG")
        child = department_create(name="Platform", code="PLT", parent=parent)

        self.assertEqual(child.parent, parent)

    def test_blank_code_persists_as_null(self):
        department = department_create(name="Codeless")

        self.assertIsNone(department.code)


class PositionCreateTests(BaseTenantTestCase):
    def test_creates_position(self):
        position = position_create(title="Manager", code="MGR")

        self.assertEqual(position.title, "Manager")
        self.assertEqual(position.code, "MGR")
        self.assertTrue(Position.objects.filter(code="MGR").exists())

    def test_supports_nested_positions(self):
        parent = position_factory(title="Engineering", code="ENG")
        child = position_create(title="Backend Lead", code="BE-LEAD", parent=parent)

        self.assertEqual(child.parent, parent)


class PermissionCreateTests(BaseTenantTestCase):
    def test_creates_permission(self):
        permission = permission_create(
            codename="view_employees",
            name="View Employees",
            description="Read-only access to employee records",
        )

        self.assertEqual(permission.codename, "view_employees")
        self.assertEqual(permission.name, "View Employees")
        self.assertTrue(Permission.objects.filter(codename="view_employees").exists())

    def test_rejects_duplicate_codename(self):
        permission_create(codename="view_employees", name="View Employees")

        with self.assertRaises((ValidationError, IntegrityError)):
            permission_create(codename="view_employees", name="View Employees Again")


class RoleCreateTests(BaseTenantTestCase):
    def test_creates_role(self):
        role = role_create(name="Manager")

        self.assertEqual(role.name, "Manager")
        self.assertFalse(role.is_system)
        self.assertTrue(Role.objects.filter(name="Manager").exists())

    def test_creates_system_role(self):
        role = role_create(name="Admin", is_system=True)

        self.assertTrue(role.is_system)

    def test_attaches_permissions(self):
        view_perm = permission_factory(codename="view_employees", name="View")
        add_perm = permission_factory(codename="add_employees", name="Add")

        role = role_create(name="HR Manager", permissions=[view_perm, add_perm])

        self.assertEqual(set(role.permissions.all()), {view_perm, add_perm})

    def test_rejects_duplicate_name(self):
        role_create(name="Manager")

        with self.assertRaises((ValidationError, IntegrityError)):
            role_create(name="Manager")


class PermissionCatalogEnsureTests(BaseTenantTestCase):
    def test_creates_catalog_rows(self):
        from employees.permission_catalog import permission_catalog_entries

        permission_catalog_ensure()
        entries = permission_catalog_entries()
        codenames = [entry["codename"] for entry in entries]

        self.assertEqual(
            Permission.objects.filter(codename__in=codenames).count(),
            len(entries),
        )

    def test_is_idempotent(self):
        first = permission_catalog_ensure()
        second = permission_catalog_ensure()

        self.assertEqual(len(first), len(second))
        self.assertEqual(
            Permission.objects.filter(codename=first[0].codename).count(),
            1,
        )

    def test_updates_name_and_description(self):
        from employees.permission_catalog import PermissionCodename

        permission_catalog_ensure()
        permission = Permission.objects.get(codename=PermissionCodename.EMPLOYEES_VIEW)
        permission.name = "Old name"
        permission.description = "Old description"
        permission.save(update_fields=["name", "description"])

        permission_catalog_ensure()
        permission.refresh_from_db()

        self.assertEqual(permission.name, PermissionCodename.EMPLOYEES_VIEW.label)
        self.assertEqual(permission.description, "View the employee directory.")


class EmployeeRoleEnsureTests(BaseTenantTestCase):
    def test_creates_system_role_with_own_attendance_only(self):
        from employees.permission_catalog import (
            EMPLOYEE_ROLE_NAME,
            PermissionCodename,
        )

        role = employee_role_ensure()

        self.assertEqual(role.name, EMPLOYEE_ROLE_NAME)
        self.assertTrue(role.is_system)
        self.assertEqual(
            list(role.permissions.values_list("codename", flat=True)),
            [PermissionCodename.ATTENDANCE_OWN_VIEW],
        )

    def test_is_idempotent(self):
        first = employee_role_ensure()
        second = employee_role_ensure()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Role.objects.filter(name=first.name).count(), 1)

    def test_assigns_non_admin_employees_and_skips_staff(self):
        from tenant_users.permissions.models import UserTenantPermissions

        from employees.permission_catalog import EMPLOYEE_ROLE_NAME

        worker = employee_factory(first_name="Worker", emp_code="ROLE-W")
        staff_member = employee_factory(first_name="Staffer", emp_code="ROLE-S")
        UserTenantPermissions.objects.update_or_create(
            profile=staff_member.user,
            defaults={"is_staff": True},
        )
        other_role = role_create(name="Temp Role")
        worker.role = None
        worker.save(update_fields=["role"])
        staff_member.role = other_role
        staff_member.save(update_fields=["role"])

        updated = employees_assign_employee_role()

        worker.refresh_from_db()
        staff_member.refresh_from_db()
        self.assertGreaterEqual(updated, 1)
        self.assertEqual(worker.role.name, EMPLOYEE_ROLE_NAME)
        self.assertEqual(staff_member.role, other_role)
