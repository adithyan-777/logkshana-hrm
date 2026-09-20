"""Round name-avatar: model helpers + template tag (no DB needed)."""

from django.template import Context, Template
from django.test import SimpleTestCase

from employees.models import Employee


class EmployeeAvatarHelpersTest(SimpleTestCase):
    def test_initials_first_last(self):
        emp = Employee(first_name="Adithyan", last_name="Krishna")
        self.assertEqual(emp.initials, "AK")

    def test_initials_single_name(self):
        emp = Employee(first_name="Madonna")
        self.assertEqual(emp.initials, "MA")

    def test_initials_fallback_code(self):
        emp = Employee(first_name="", last_name="", emp_code="E042")
        self.assertEqual(emp.initials, "E0")

    def test_variant_stable_and_ranged(self):
        emp = Employee(first_name="Jane", last_name="Doe")
        first = emp.avatar_variant
        self.assertGreaterEqual(first, 0)
        self.assertLess(first, 8)
        self.assertEqual(Employee(first_name="Jane", last_name="Doe").avatar_variant, first)

    def test_avatar_tag_renders_round_span(self):
        emp = Employee(first_name="Jane", last_name="Doe", emp_code="E001")
        html = Template("{% load avatar %}{% avatar employee size='sm' %}").render(
            Context({"employee": emp})
        )
        self.assertIn("emp-avatar", html)
        self.assertIn("emp-avatar--sm", html)
        self.assertIn("JD", html)
        self.assertIn(f"emp-avatar--{emp.avatar_variant}", html)
