from django.core.exceptions import ValidationError

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    department_factory,
    employee_factory,
    permission_factory,
    position_factory,
    role_factory,
)
from employees.models import Department, Employee, Permission, Position, Role
from employees.selectors import (
    department_list,
    employee_get,
    employee_get_by_emp_code,
    employee_get_for_user,
    employee_list,
    permission_list,
    position_list,
    role_list,
    user_has_permission,
    user_permission_codenames,
)
from employees.services import employee_role_ensure


class EmployeeListTests(BaseTenantTestCase):
    def test_returns_employees_newest_first(self):
        employee_factory(first_name="Charlie", emp_code="C002")
        employee_factory(first_name="Alice", emp_code="A001")
        employee_factory(first_name="Bob", emp_code="B001")

        results = list(employee_list())

        self.assertEqual(
            [e.emp_code for e in results], ["B001", "A001", "C002"]
        )

    def test_filters_by_first_name(self):
        employee_factory(first_name="Alice", emp_code="E100")
        employee_factory(first_name="Bob", emp_code="E101")

        results = list(employee_list(search="alice"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].first_name, "Alice")

    def test_filters_by_emp_code(self):
        employee_factory(first_name="One", emp_code="SEARCH-ME")
        employee_factory(first_name="Two", emp_code="OTHER")

        results = list(employee_list(search="search-me"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].emp_code, "SEARCH-ME")

    def test_filters_by_email(self):
        employee_factory(
            first_name="Email", emp_code="E110", email="unique@example.com"
        )
        employee_factory(first_name="Other", emp_code="E111", email="other@example.com")

        results = list(employee_list(search="unique@example.com"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].email, "unique@example.com")

    def test_excludes_soft_deleted_employees(self):
        employee = employee_factory(first_name="Deleted", emp_code="E120")
        employee.delete()

        self.assertEqual(employee_list().count(), 0)
        self.assertEqual(Employee.all_objects.count(), 1)


class EmployeeGetByEmpCodeTests(BaseTenantTestCase):
    def test_returns_active_employee(self):
        employee = employee_factory(first_name="Punch", emp_code="E001")

        found = employee_get_by_emp_code(emp_code="E001")

        self.assertEqual(found, employee)

    def test_returns_none_for_unknown_code(self):
        self.assertIsNone(employee_get_by_emp_code(emp_code="MISSING"))

    def test_returns_none_for_inactive_employee(self):
        employee_factory(first_name="Gone", emp_code="E002", is_active=False)

        self.assertIsNone(employee_get_by_emp_code(emp_code="E002"))

    def test_raises_when_duplicate_active_codes(self):
        employee_factory(first_name="One", last_name="Dup", emp_code="DUP")
        employee_factory(first_name="Two", last_name="Dup", emp_code="DUP")

        with self.assertRaises(ValidationError) as ctx:
            employee_get_by_emp_code(emp_code="DUP")

        self.assertIn("employee_id", ctx.exception.message_dict)


class DepartmentListTests(BaseTenantTestCase):
    def test_returns_departments_ordered_by_name(self):
        department_factory(name="Sales", code="SAL")
        department_factory(name="Engineering", code="ENG")

        results = list(department_list())

        self.assertEqual([d.name for d in results], ["Engineering", "Sales"])

    def test_filters_by_name(self):
        department_factory(name="Engineering", code="ENG")
        department_factory(name="Sales", code="SAL")

        results = list(department_list(search="eng"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "ENG")

    def test_filters_by_code(self):
        department_factory(name="Engineering", code="ENG")
        department_factory(name="Sales", code="SAL")

        results = list(department_list(search="sal"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Sales")

    def test_excludes_soft_deleted_departments(self):
        department = department_factory(name="Deleted", code="DEL")
        department.delete()

        self.assertEqual(department_list().count(), 0)
        self.assertEqual(Department.all_objects.count(), 1)


class PositionListTests(BaseTenantTestCase):
    def test_returns_positions_ordered_by_title(self):
        position_factory(title="Manager", code="MGR")
        position_factory(title="Analyst", code="ANL")

        results = list(position_list())

        self.assertEqual([p.title for p in results], ["Analyst", "Manager"])

    def test_filters_by_title(self):
        position_factory(title="Manager", code="MGR")
        position_factory(title="Analyst", code="ANL")

        results = list(position_list(search="man"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "MGR")

    def test_filters_by_code(self):
        position_factory(title="Manager", code="MGR")
        position_factory(title="Analyst", code="ANL")

        results = list(position_list(search="anl"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Analyst")

    def test_excludes_soft_deleted_positions(self):
        position = position_factory(title="Deleted", code="DEL")
        position.delete()

        self.assertEqual(position_list().count(), 0)
        self.assertEqual(Position.all_objects.count(), 1)


class RoleListTests(BaseTenantTestCase):
    def test_returns_roles_ordered_by_name(self):
        employee_role_ensure()
        role_factory(name="Manager")
        role_factory(name="Admin")

        results = list(role_list())

        self.assertEqual([r.name for r in results], ["Admin", "Employee", "Manager"])

    def test_filters_by_name(self):
        role_factory(name="Manager")
        role_factory(name="Admin")

        results = list(role_list(search="man"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Manager")

    def test_excludes_soft_deleted_roles(self):
        role = role_factory(name="Deleted")
        role.delete()

        self.assertFalse(role_list().filter(pk=role.pk).exists())
        self.assertTrue(Role.all_objects.filter(pk=role.pk).exists())


class PermissionListTests(BaseTenantTestCase):
    def test_returns_permissions_ordered_by_codename(self):
        permission_factory(codename="view_reports", name="View Reports")
        permission_factory(codename="add_employee", name="Add Employee")

        results = list(permission_list())
        codenames = [p.codename for p in results]

        self.assertEqual(codenames, sorted(codenames))
        self.assertIn("add_employee", codenames)
        self.assertIn("view_reports", codenames)

    def test_filters_by_codename(self):
        permission_factory(codename="zz_unique_codename", name="Other")
        permission_factory(codename="add_employee", name="Add Employee")

        results = list(permission_list(search="zz_unique"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].codename, "zz_unique_codename")

    def test_filters_by_name(self):
        permission_factory(codename="view_reports", name="Unique Report Label")
        permission_factory(codename="add_employee", name="Add Employee")

        results = list(permission_list(search="unique report label"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].codename, "view_reports")

    def test_filters_by_description(self):
        permission_factory(
            codename="view_reports",
            name="View Reports",
            description="Quarterly summary",
        )
        permission_factory(
            codename="add_employee",
            name="Add Employee",
            description="Onboarding flow",
        )

        results = list(permission_list(search="quarterly"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].codename, "view_reports")

    def test_excludes_soft_deleted_permissions(self):
        permission = permission_factory(codename="deleted_perm", name="Deleted")
        permission.delete()

        self.assertEqual(permission_list().filter(pk=permission.pk).exists(), False)
        self.assertTrue(Permission.all_objects.filter(pk=permission.pk).exists())


class UserHasPermissionTests(BaseTenantTestCase):
    def test_unauthenticated_user_has_no_permission(self):
        from types import SimpleNamespace

        user = SimpleNamespace(is_authenticated=False, is_superuser=False)

        self.assertFalse(user_has_permission(user=user, codename="test.view"))

    def test_user_without_employee_has_no_permission(self):
        employee = employee_factory(first_name="NoRole", emp_code="PERM-NE")

        self.assertFalse(user_has_permission(user=employee.user, codename="test.view"))

    def test_employee_without_role_has_no_permission(self):
        employee = employee_factory(first_name="NoRole", emp_code="PERM-NR")
        employee.role = None
        employee.save(update_fields=["role"])

        self.assertFalse(user_has_permission(user=employee.user, codename="test.view"))

    def test_employee_with_role_permission(self):
        permission = permission_factory(codename="test.view", name="Test View")
        role = role_factory(name="Viewer", permissions=[permission])
        employee = employee_factory(first_name="HasRole", emp_code="PERM-HR")
        employee.role = role
        employee.save(update_fields=["role"])

        self.assertTrue(user_has_permission(user=employee.user, codename="test.view"))
        self.assertFalse(
            user_has_permission(user=employee.user, codename="test.missing")
        )

    def test_superuser_has_any_permission(self):
        from types import SimpleNamespace

        user = SimpleNamespace(
            is_authenticated=True, is_superuser=True, is_staff=False, pk=None
        )

        self.assertTrue(user_has_permission(user=user, codename="missing.perm"))

    def test_staff_has_any_permission(self):
        from types import SimpleNamespace

        user = SimpleNamespace(
            is_authenticated=True, is_superuser=False, is_staff=True, pk=None
        )

        self.assertTrue(user_has_permission(user=user, codename="missing.perm"))

    def test_tenant_owner_has_any_permission(self):
        self.assertTrue(
            user_has_permission(user=self.tenant.owner, codename="missing.perm")
        )

    def test_staff_test_user_has_admin_bypass(self):
        self.assertTrue(user_has_permission(user=self.user, codename="missing.perm"))


class EmployeeGetForUserTests(BaseTenantTestCase):
    def test_returns_linked_employee(self):
        employee = employee_factory(first_name="Linked", emp_code="LINK-1")

        self.assertEqual(employee_get_for_user(user=employee.user), employee)

    def test_returns_none_when_unlinked(self):
        self.assertIsNone(employee_get_for_user(user=self.user))


class EmployeeGetTests(BaseTenantTestCase):
    def test_returns_employee_by_id(self):
        employee = employee_factory(first_name="Lookup", emp_code="GET-1")

        self.assertEqual(employee_get(employee_id=employee.pk), employee)

    def test_returns_none_for_missing_id(self):
        self.assertIsNone(employee_get(employee_id=999999))


class UserPermissionCodenamesTests(BaseTenantTestCase):
    def test_admin_returns_none(self):
        self.assertIsNone(user_permission_codenames(user=self.user))

    def test_employee_returns_own_attendance(self):
        from employees.permission_catalog import PermissionCodename

        employee = employee_factory(first_name="Coder", emp_code="COD-1")

        self.assertEqual(
            user_permission_codenames(user=employee.user),
            frozenset({PermissionCodename.ATTENDANCE_OWN_VIEW}),
        )
