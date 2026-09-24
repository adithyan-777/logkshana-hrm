from django.urls import reverse

from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import (
    department_factory,
    employee_factory,
    position_factory,
)
from employees.models import Department, Employee, Position


class EditDeleteTestMixin:
    def _login_as_plain_user(self, *, first_name="NoPerm", emp_code):
        employee = employee_factory(first_name=first_name, emp_code=emp_code)
        user = employee.user
        user.set_password(TEST_PASSWORD)
        user.save()
        self.login_as(user=user)
        return user


class EmployeeDeleteTests(EditDeleteTestMixin, BaseTenantTestCase):
    def test_delete_soft_deletes_deactivates_user_and_triggers(self):
        employee = employee_factory(first_name="Gone", emp_code="E-DEL-1")
        user_id = employee.user_id

        response = self.client.delete(reverse("employee_delete", args=[employee.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "employeeDeleted")
        self.assertFalse(Employee.objects.filter(pk=employee.pk).exists())
        self.assertTrue(Employee.all_objects.filter(pk=employee.pk).exists())
        user = Employee.all_objects.get(pk=employee.pk).user
        self.assertEqual(user.pk, user_id)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_delete_without_perm_forbidden(self):
        employee = employee_factory(first_name="Stay", emp_code="E-DEL-2")
        self._login_as_plain_user(emp_code="E-DEL-NOPERM")

        response = self.client.delete(reverse("employee_delete", args=[employee.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Employee.objects.filter(pk=employee.pk).exists())

    def test_delete_missing_returns_404(self):
        response = self.client.delete(reverse("employee_delete", args=[999999]))

        self.assertEqual(response.status_code, 404)


class DepartmentEditDeleteTests(EditDeleteTestMixin, BaseTenantTestCase):
    def test_edit_get_redirects_to_list_drawer(self):
        department = department_factory(name="EditMe", code="EDM")

        response = self.client.get(reverse("department_edit", args=[department.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("department_list"), response.url)
        self.assertIn("drawer=", response.url)

    def test_edit_post_updates_and_triggers(self):
        department = department_factory(name="Before", code="BEF")

        response = self.client.post(
            reverse("department_edit", args=[department.pk]),
            {"name": "After", "code": "AFT", "parent": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "departmentUpdated")
        department.refresh_from_db()
        self.assertEqual(department.name, "After")
        self.assertEqual(department.code, "AFT")

    def test_delete_soft_deletes_and_triggers(self):
        department = department_factory(name="Gone", code="GONE")

        response = self.client.delete(
            reverse("department_delete", args=[department.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "departmentDeleted")
        self.assertFalse(Department.objects.filter(pk=department.pk).exists())
        self.assertTrue(Department.all_objects.filter(pk=department.pk).exists())

    def test_delete_without_perm_forbidden(self):
        department = department_factory(name="Stay", code="STAY")
        self._login_as_plain_user(emp_code="E-DEPT-NOPERM")

        response = self.client.delete(
            reverse("department_delete", args=[department.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Department.objects.filter(pk=department.pk).exists())

    def test_delete_missing_returns_404(self):
        response = self.client.delete(reverse("department_delete", args=[999999]))

        self.assertEqual(response.status_code, 404)


class PositionEditDeleteTests(EditDeleteTestMixin, BaseTenantTestCase):
    def test_edit_get_redirects_to_list_drawer(self):
        position = position_factory(title="EditMe", code="EDM")

        response = self.client.get(reverse("position_edit", args=[position.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("position_list"), response.url)
        self.assertIn("drawer=", response.url)

    def test_edit_post_updates_and_triggers(self):
        position = position_factory(title="Before", code="BEF")

        response = self.client.post(
            reverse("position_edit", args=[position.pk]),
            {"title": "After", "code": "AFT", "parent": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "positionUpdated")
        position.refresh_from_db()
        self.assertEqual(position.title, "After")
        self.assertEqual(position.code, "AFT")

    def test_delete_soft_deletes_and_triggers(self):
        position = position_factory(title="Gone", code="GONE")

        response = self.client.delete(reverse("position_delete", args=[position.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "positionDeleted")
        self.assertFalse(Position.objects.filter(pk=position.pk).exists())
        self.assertTrue(Position.all_objects.filter(pk=position.pk).exists())

    def test_delete_without_perm_forbidden(self):
        position = position_factory(title="Stay", code="STAY")
        self._login_as_plain_user(emp_code="E-POS-NOPERM")

        response = self.client.delete(reverse("position_delete", args=[position.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Position.objects.filter(pk=position.pk).exists())

    def test_delete_missing_returns_404(self):
        response = self.client.delete(reverse("position_delete", args=[999999]))

        self.assertEqual(response.status_code, 404)
