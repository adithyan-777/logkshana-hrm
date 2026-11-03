"""Employee drawer: editing the linked login username."""

import json

from django.urls import reverse

from common.tests.base import BaseTenantTestCase
from common.tests.factories import employee_factory
from employees.models import Employee


class EmployeeUsernameEditTests(BaseTenantTestCase):
    def _url(self, employee):
        return reverse("employee_edit", args=[employee.pk])

    def _payload(self, employee, **overrides):
        data = {
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "emp_code": employee.emp_code,
            "email": employee.email,
            "mobile": employee.mobile,
            "username": employee.user.username,
            "is_active": "on",
        }
        data.update(overrides)
        return data

    def test_edit_updates_username(self):
        employee = employee_factory(
            first_name="Rename", last_name="Me", emp_code="E-UN-01"
        )

        response = self.client.post(
            self._url(employee),
            self._payload(employee, username="renamed.employee"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("employeeUpdated", response.headers.get("HX-Trigger"))
        employee.user.refresh_from_db()
        self.assertEqual(employee.user.username, "renamed.employee")

    def test_edit_keeps_own_username(self):
        employee = employee_factory(
            first_name="Keep", last_name="Mine", emp_code="E-UN-02"
        )
        original = employee.user.username

        response = self.client.post(self._url(employee), self._payload(employee))

        self.assertEqual(response.status_code, 200)
        self.assertIn("employeeUpdated", response.headers.get("HX-Trigger"))
        employee.user.refresh_from_db()
        self.assertEqual(employee.user.username, original)

    def test_duplicate_username_case_insensitive_keeps_drawer_open(self):
        other = employee_factory(
            first_name="Taken", last_name="Name", emp_code="E-UN-03"
        )
        employee = employee_factory(
            first_name="Main", last_name="Person", emp_code="E-UN-04"
        )
        original = employee.user.username

        response = self.client.post(
            self._url(employee),
            self._payload(employee, username=other.user.username.upper()),
        )

        self.assertEqual(response.status_code, 200)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertNotIn("closeModal", trigger)
        self.assertEqual(trigger["showToast"]["type"], "error")
        self.assertIn("Login username", trigger["showToast"]["message"])
        self.assertContains(response, "This username is already in use.")
        employee.user.refresh_from_db()
        self.assertEqual(employee.user.username, original)

    def test_blank_username_rejected(self):
        employee = employee_factory(
            first_name="Blank", last_name="Name", emp_code="E-UN-05"
        )
        original = employee.user.username

        response = self.client.post(
            self._url(employee),
            self._payload(employee, username=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        employee.user.refresh_from_db()
        self.assertEqual(employee.user.username, original)

    def test_employee_without_user_has_no_username_field(self):
        employee = Employee.objects.create(
            first_name="No", last_name="Account", emp_code="E-UN-06"
        )

        response = self.client.get(
            self._url(employee),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="username"')

    def test_employee_without_user_still_saves(self):
        employee = Employee.objects.create(
            first_name="No", last_name="Account", emp_code="E-UN-07"
        )

        response = self.client.post(
            self._url(employee),
            {
                "first_name": "No",
                "last_name": "Changed",
                "emp_code": "E-UN-07",
                "email": "",
                "mobile": "",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("employeeUpdated", response.headers.get("HX-Trigger"))
        employee.refresh_from_db()
        self.assertEqual(employee.last_name, "Changed")

    def test_edit_form_prefills_current_username(self):
        employee = employee_factory(
            first_name="Prefill", last_name="User", emp_code="E-UN-08"
        )

        response = self.client.get(
            self._url(employee),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{employee.user.username}"')
