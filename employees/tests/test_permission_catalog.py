from types import SimpleNamespace

from django.test import SimpleTestCase

from employees.permission_catalog import (
    permissions_grouped_choices,
    permission_module_label,
)


class PermissionModuleLabelTests(SimpleTestCase):
    def test_uses_catalog_module_heading(self):
        self.assertEqual(permission_module_label("employees.view"), "Employees")
        self.assertEqual(permission_module_label("leave.types.manage"), "Leave")

    def test_unknown_codename_goes_to_other(self):
        self.assertEqual(permission_module_label("custom.thing"), "Other")
        self.assertEqual(permission_module_label("noperiod"), "Other")


class PermissionsGroupedChoicesTests(SimpleTestCase):
    def test_groups_by_module_in_catalog_order(self):
        permissions = [
            SimpleNamespace(pk=1, name="View employees", codename="employees.view"),
            SimpleNamespace(pk=2, name="Add employees", codename="employees.add"),
            SimpleNamespace(pk=3, name="View dashboard", codename="dashboard.view"),
            SimpleNamespace(pk=4, name="Custom", codename="legacy.view"),
        ]

        grouped = permissions_grouped_choices(permissions)

        self.assertEqual(
            grouped,
            [
                ("Dashboard", [(3, "View dashboard")]),
                ("Employees", [(1, "View employees"), (2, "Add employees")]),
                ("Other", [(4, "Custom")]),
            ],
        )

    def test_labels_are_names_only(self):
        permissions = [
            SimpleNamespace(pk=9, name="View reports", codename="reports.view"),
        ]

        grouped = permissions_grouped_choices(permissions)

        self.assertEqual(grouped, [("Reports", [(9, "View reports")])])
        self.assertNotIn("reports.view", str(grouped))
