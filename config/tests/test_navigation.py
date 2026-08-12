from django.http import HttpRequest
from django.test import SimpleTestCase

from config.context_processors import navigation
from config.navigation import (
    BREADCRUMBS,
    LIST_ACTIONS,
    active_section,
    breadcrumbs_for,
    page_action_for,
)


class NavigationHelpersTests(SimpleTestCase):
    def _request(self, path: str, url_name: str | None = None) -> HttpRequest:
        request = HttpRequest()
        request.path = path
        if url_name is not None:
            request.resolver_match = type("Match", (), {"url_name": url_name})()
        return request

    def test_active_section_for_leave_path(self):
        request = self._request("/leave/types/")
        self.assertEqual(active_section(request), "leave")

    def test_active_section_for_schedule_path(self):
        request = self._request("/schedule/shifts/")
        self.assertEqual(active_section(request), "schedule")

    def test_active_section_for_reports_path(self):
        request = self._request("/reports/exceptions/")
        self.assertEqual(active_section(request), "reports")

    def test_active_section_returns_none_outside_collapsible_sections(self):
        request = self._request("/employees/")
        self.assertIsNone(active_section(request))

    def test_breadcrumbs_for_employee_list(self):
        request = self._request("/employees/", "employee_list")
        crumbs = breadcrumbs_for(request)
        self.assertEqual(len(crumbs), 2)
        self.assertEqual(crumbs[0], ("Dashboard", "dashboard"))
        self.assertEqual(crumbs[1], ("Employees", None))

    def test_breadcrumbs_for_employee_add(self):
        request = self._request("/employees/add/", "employee_add")
        crumbs = breadcrumbs_for(request)
        self.assertEqual(len(crumbs), 3)
        self.assertEqual(crumbs[-1], ("Add employee", None))

    def test_page_action_for_employee_list(self):
        request = self._request("/employees/", "employee_list")
        self.assertEqual(page_action_for(request), ("Add employee", "employee_add"))

    def test_page_action_returns_none_for_add_pages(self):
        request = self._request("/employees/add/", "employee_add")
        self.assertIsNone(page_action_for(request))

    def test_context_processor_returns_navigation_keys(self):
        request = self._request("/leave/requests/", "leave_request_list")
        context = navigation(request)
        self.assertEqual(context["nav_section"], "leave")
        self.assertEqual(len(context["breadcrumbs"]), 3)
        self.assertEqual(context["page_action"], LIST_ACTIONS["leave_request_list"])

    def test_breadcrumb_map_covers_all_list_and_add_routes(self):
        expected = {
            name
            for name in BREADCRUMBS
            if name.endswith("_list") or name.endswith("_add") or name.startswith("report_")
        }
        self.assertIn("employee_list", expected)
        self.assertIn("report_attendance_summary", expected)
        for url_name in expected:
            self.assertIn(url_name, BREADCRUMBS, msg=url_name)
