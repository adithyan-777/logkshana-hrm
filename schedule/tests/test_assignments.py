"""Schedule assignments: by department, person by person, bulk with excludes."""

from datetime import date

from django.urls import reverse

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    department_factory,
    employee_factory,
    schedule_factory,
)
from schedule.models import EmployeeScheduleAssignment
from schedule.services import resolve_assignment_employees


class ResolveAssignmentEmployeesTests(BaseTenantTestCase):
    def test_department_mode_picks_active_members(self):
        engineering = department_factory(name="Engineering", code="ENG")
        sales = department_factory(name="Sales", code="SAL")
        alice = employee_factory(
            first_name="Alice", emp_code="A001", department=engineering
        )
        bob = employee_factory(
            first_name="Bob", emp_code="B001", department=engineering
        )
        employee_factory(first_name="Cara", emp_code="C001", department=sales)

        resolved = resolve_assignment_employees(
            mode="department", departments=[engineering]
        )

        self.assertEqual({e.pk for e in resolved}, {alice.pk, bob.pk})

    def test_individual_mode_picks_exact_people(self):
        alice = employee_factory(first_name="Alice", emp_code="A001")
        bob = employee_factory(first_name="Bob", emp_code="B001")
        employee_factory(first_name="Cara", emp_code="C001")

        resolved = resolve_assignment_employees(
            mode="individual", employees=[alice, bob]
        )

        self.assertEqual({e.pk for e in resolved}, {alice.pk, bob.pk})

    def test_all_except_mode_excludes_selected(self):
        alice = employee_factory(first_name="Alice", emp_code="A001")
        bob = employee_factory(first_name="Bob", emp_code="B001")
        cara = employee_factory(first_name="Cara", emp_code="C001")

        resolved = resolve_assignment_employees(
            mode="all_except", excluded=[cara]
        )

        self.assertEqual({e.pk for e in resolved}, {alice.pk, bob.pk})

    def test_inactive_employees_never_resolved(self):
        active = employee_factory(first_name="Active", emp_code="A001")
        quiet = employee_factory(first_name="Quiet", emp_code="Q001", is_active=False)

        resolved = resolve_assignment_employees(
            mode="individual", employees=[active, quiet]
        )

        self.assertEqual([e.pk for e in resolved], [active.pk])


class AssignmentAddViewTests(BaseTenantTestCase):
    def _post(self, schedule, **overrides):
        data = {
            "schedule": str(schedule.pk),
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "priority": "0",
            "name": "",
        }
        data.update(overrides)
        return self.client.post(reverse("assignment_add"), data)

    def test_add_by_department(self):
        engineering = department_factory(name="Engineering", code="ENG")
        alice = employee_factory(
            first_name="Alice", emp_code="A001", department=engineering
        )
        employee_factory(first_name="Outsider", emp_code="O001")
        schedule = schedule_factory(name="Week")

        response = self._post(
            schedule, mode="department", departments=[str(engineering.pk)]
        )

        self.assertIsNotNone(response.headers.get("HX-Trigger"))
        assignment = EmployeeScheduleAssignment.objects.get(schedule=schedule)
        self.assertEqual({e.pk for e in assignment.employees.all()}, {alice.pk})

    def test_add_person_by_person(self):
        alice = employee_factory(first_name="Alice", emp_code="A001")
        bob = employee_factory(first_name="Bob", emp_code="B001")
        employee_factory(first_name="Cara", emp_code="C001")
        schedule = schedule_factory(name="Week")

        response = self._post(
            schedule,
            mode="individual",
            employees=[str(alice.pk), str(bob.pk)],
        )

        self.assertIsNotNone(response.headers.get("HX-Trigger"))
        assignment = EmployeeScheduleAssignment.objects.get(schedule=schedule)
        self.assertEqual(
            {e.pk for e in assignment.employees.all()}, {alice.pk, bob.pk}
        )

    def test_mass_add_with_exclude(self):
        alice = employee_factory(first_name="Alice", emp_code="A001")
        bob = employee_factory(first_name="Bob", emp_code="B001")
        cara = employee_factory(first_name="Cara", emp_code="C001")
        schedule = schedule_factory(name="Week")

        response = self._post(
            schedule,
            mode="all_except",
            excluded_employees=[str(cara.pk)],
        )

        self.assertIsNotNone(response.headers.get("HX-Trigger"))
        assignment = EmployeeScheduleAssignment.objects.get(schedule=schedule)
        self.assertEqual(
            {e.pk for e in assignment.employees.all()}, {alice.pk, bob.pk}
        )

    def test_empty_selection_rejected(self):
        department_factory(name="Empty", code="EMP")
        schedule = schedule_factory(name="Week")

        response = self._post(schedule, mode="individual")

        self.assertIsNone(response.headers.get("HX-Trigger"))
        self.assertEqual(
            EmployeeScheduleAssignment.objects.filter(schedule=schedule).count(), 0
        )

    def test_end_before_start_rejected(self):
        alice = employee_factory(first_name="Alice", emp_code="A001")
        schedule = schedule_factory(name="Week")

        response = self._post(
            schedule,
            mode="individual",
            employees=[str(alice.pk)],
            start_date="2026-12-31",
            end_date="2026-01-01",
        )

        self.assertIsNone(response.headers.get("HX-Trigger"))
        self.assertEqual(
            EmployeeScheduleAssignment.objects.filter(schedule=schedule).count(), 0
        )

    def test_list_returns_200(self):
        response = self.client.get(reverse("assignment_list"))

        self.assertEqual(response.status_code, 200)

    def test_end_date_defaults_to_open_ended(self):
        alice = employee_factory(first_name="Alice", emp_code="A001")
        schedule = schedule_factory(name="Week")

        response = self._post(
            schedule,
            mode="individual",
            employees=[str(alice.pk)],
            end_date="",
        )

        self.assertIsNotNone(response.headers.get("HX-Trigger"))
        assignment = EmployeeScheduleAssignment.objects.get(schedule=schedule)
        self.assertIsNone(assignment.end_date)
        self.assertEqual(date(2026, 1, 1), assignment.start_date)
