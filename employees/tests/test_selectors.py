from common.tests.base import BaseTenantTestCase
from common.tests.factories import department_factory, employee_factory
from employees.models import Employee
from employees.selectors import employee_list


class EmployeeListTests(BaseTenantTestCase):
    def test_returns_employees_ordered_by_code_then_first_name(self):
        employee_factory(first_name="Charlie", emp_code="C002")
        employee_factory(first_name="Alice", emp_code="A001")
        employee_factory(first_name="Bob", emp_code="B001")

        results = list(employee_list())

        self.assertEqual([e.emp_code for e in results], ["A001", "B001", "C002"])

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
        employee_factory(first_name="Email", emp_code="E110", email="unique@example.com")
        employee_factory(first_name="Other", emp_code="E111", email="other@example.com")

        results = list(employee_list(search="unique@example.com"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].email, "unique@example.com")

    def test_excludes_soft_deleted_employees(self):
        employee = employee_factory(first_name="Deleted", emp_code="E120")
        employee.delete()

        self.assertEqual(employee_list().count(), 0)
        self.assertEqual(Employee.all_objects.count(), 1)
