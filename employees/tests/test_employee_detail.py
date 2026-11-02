import json
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.models import AttendanceActivity
from common.localtime import local_date
from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import activity_factory, employee_factory
from employees.models import Employee, Permission, Role
from employees.permission_catalog import PermissionCodename

User = get_user_model()


class EmployeeDetailTests(BaseTenantTestCase):
    def _login_with_permissions(self, *codenames):
        with schema_context(get_public_schema_name()):
            user = User.objects.create_user(
                username="detail_reader", password=TEST_PASSWORD
            )
            self.tenant.add_user(user)

        role = Role.objects.create(name="Detail reader")
        for codename in codenames:
            permission, _ = Permission.objects.get_or_create(
                codename=codename, defaults={"name": str(codename)}
            )
            role.permissions.add(permission)
        Employee.objects.create(
            first_name="Reader", emp_code="DETAIL-READER", user=user, role=role
        )
        self.login_as(user=user, via="username")

    def test_directory_links_to_detail_and_keeps_punch_read_only(self):
        employee = employee_factory(first_name="Profile", emp_code="DETAIL-1")
        employee_factory(first_name="No status", emp_code="DETAIL-EMPTY")
        activity_factory(employee=employee, direction=AttendanceActivity.Direction.IN)

        response = self.client.get(reverse("employee_list"))

        self.assertContains(response, reverse("employee_detail", args=[employee.pk]))
        # The directory table shows no punch badges: status lives on the
        # detail page, and punch actions are the badge toggle there.
        self.assertNotContains(response, "badge punch-in")
        self.assertNotContains(response, "Status unavailable")
        self.assertNotContains(response, "badge hover-swap")
        self.assertNotContains(
            response, reverse("employee_punch_toggle", args=[employee.pk])
        )

    def test_detail_requires_login_and_employee_permission(self):
        employee = employee_factory(first_name="Private", emp_code="DETAIL-2")
        url = reverse("employee_detail", args=[employee.pk])
        anonymous = TenantClient(self.tenant)
        self.assertEqual(anonymous.get(url).status_code, 302)

        self._login_with_permissions()
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_overview_renders_employee_data_and_standard_tabs(self):
        employee = employee_factory(
            first_name="Amina", last_name="Rahman", emp_code="DETAIL-3"
        )
        response = self.client.get(reverse("employee_detail", args=[employee.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amina Rahman")
        self.assertContains(response, "DETAIL-3")
        self.assertContains(response, 'class="tabs employee-detail__tabs"')
        self.assertContains(response, 'class="tab is-active"')
        self.assertContains(response, "?tab=attendance")
        punch_url = reverse("employee_punch_toggle", args=[employee.pk])
        edit_url = reverse("employee_edit", args=[employee.pk])
        self.assertContains(response, punch_url, count=1)
        self.assertLess(
            response.content.index(punch_url.encode()),
            response.content.index(edit_url.encode()),
        )

    def test_history_is_scoped_to_employee_and_ordered_newest_first(self):
        employee = employee_factory(first_name="Target", emp_code="DETAIL-4")
        other = employee_factory(first_name="Other", emp_code="DETAIL-5")
        now = timezone.now()
        older = activity_factory(employee=employee, punch_time=now - timedelta(hours=2))
        newer = activity_factory(employee=employee, punch_time=now - timedelta(hours=1))
        activity_factory(employee=other, punch_time=now)

        response = self.client.get(
            reverse("employee_detail", args=[employee.pk]), {"tab": "attendance"}
        )

        self.assertEqual(list(response.context["punches"]), [newer, older])
        self.assertContains(response, "Punch history")
        self.assertContains(
            response, reverse("employee_punch_toggle", args=[employee.pk])
        )
        self.assertContains(response, 'hx-disabled-elt="this"')
        self.assertNotContains(response, reverse("transaction_edit", args=[newer.pk]))
        self.assertNotContains(response, reverse("transaction_delete", args=[newer.pk]))

    def test_history_pagination_keeps_attendance_tab(self):
        employee = employee_factory(first_name="Paged", emp_code="DETAIL-6")
        now = timezone.now()
        AttendanceActivity.objects.bulk_create(
            [
                AttendanceActivity(
                    employee=employee,
                    punch_time=now - timedelta(minutes=index),
                    direction=AttendanceActivity.Direction.IN,
                )
                for index in range(settings.DEFAULT_PAGE_SIZE + 1)
            ]
        )
        url = reverse("employee_detail", args=[employee.pk])

        first = self.client.get(url, {"tab": "attendance"})
        second = self.client.get(url, {"tab": "attendance", "page": 2})

        self.assertEqual(
            first.context["page_obj"].paginator.count, settings.DEFAULT_PAGE_SIZE + 1
        )
        # The default range (last 7 days) is derived from "today", so the
        # pagination link must pin from/to explicitly — dropping them would
        # silently recompute (and eventually shift) the range on page loads
        # across a day boundary.
        today = local_date(timezone.now())
        self.assertEqual(
            first.context["next_page_url"],
            f"{url}?tab=attendance&page=2"
            f"&from={(today - timedelta(days=6)).isoformat()}&to={today.isoformat()}",
        )
        self.assertEqual(second.context["page_obj"].number, 2)
        self.assertEqual(len(second.context["punches"]), 1)

    def test_punch_and_edit_refresh_matching_fragments(self):
        employee = employee_factory(first_name="Refresh", emp_code="DETAIL-7")
        url = reverse("employee_detail", args=[employee.pk])
        post = self.client.post(reverse("employee_punch_toggle", args=[employee.pk]))

        self.assertIn("employeePunchUpdated", json.loads(post["HX-Trigger"]))
        fragment = self.client.get(
            url,
            {"tab": "attendance", "fragment": "attendance"},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(fragment, 'id="employee-attendance-region"', count=1)
        self.assertContains(fragment, "Punch history")
        self.assertContains(fragment, "Checked in")
        self.assertNotContains(
            fragment, reverse("employee_punch_toggle", args=[employee.pk])
        )
        self.assertNotContains(fragment, 'id="spa-view"')
        self.assertEqual(fragment["HX-Push-Url"], "false")
        self.assertEqual(fragment.context["page_obj"].paginator.count, 1)

        detail = self.client.get(url, {"fragment": "detail"}, HTTP_HX_REQUEST="true")
        self.assertContains(detail, 'id="employee-detail-page"', count=1)
        self.assertNotContains(detail, 'id="spa-view"')

    def test_boosted_and_history_restore_requests_receive_full_page(self):
        employee = employee_factory(first_name="Navigation", emp_code="DETAIL-8")
        url = reverse("employee_detail", args=[employee.pk])
        for header in ("HTTP_HX_BOOSTED", "HTTP_HX_HISTORY_RESTORE_REQUEST"):
            response = self.client.get(
                url,
                {"tab": "attendance", "fragment": "attendance"},
                HTTP_HX_REQUEST="true",
                **{header: "true"},
            )
            self.assertContains(response, 'id="spa-view"')

    def test_history_is_hidden_without_attendance_view(self):
        employee = employee_factory(first_name="Target", emp_code="DETAIL-9")
        activity_factory(employee=employee)
        self._login_with_permissions(PermissionCodename.EMPLOYEES_VIEW)

        response = self.client.get(
            reverse("employee_detail", args=[employee.pk]),
            {"tab": "attendance", "fragment": "attendance"},
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "don’t have access")
        self.assertNotContains(
            response, 'class="data-table employee-detail__history-table"'
        )
        self.assertNotContains(
            response, reverse("employee_punch_toggle", args=[employee.pk])
        )

    def test_punch_permission_does_not_grant_history_access(self):
        employee = employee_factory(first_name="Target", emp_code="DETAIL-10")
        activity_factory(employee=employee)
        self._login_with_permissions(
            PermissionCodename.EMPLOYEES_VIEW, PermissionCodename.ATTENDANCE_ADD
        )

        response = self.client.get(
            reverse("employee_detail", args=[employee.pk]), {"tab": "attendance"}
        )

        self.assertContains(
            response, reverse("employee_punch_toggle", args=[employee.pk])
        )
        self.assertContains(response, "don’t have access")
        self.assertNotContains(
            response, 'class="data-table employee-detail__history-table"'
        )

    def test_history_permission_does_not_grant_punch_action(self):
        employee = employee_factory(first_name="Target", emp_code="DETAIL-11")
        activity_factory(employee=employee)
        self._login_with_permissions(
            PermissionCodename.EMPLOYEES_VIEW, PermissionCodename.ATTENDANCE_VIEW
        )

        response = self.client.get(
            reverse("employee_detail", args=[employee.pk]), {"tab": "attendance"}
        )

        self.assertContains(response, "Punch history")
        self.assertNotContains(
            response, reverse("employee_punch_toggle", args=[employee.pk])
        )

    def test_missing_employee_returns_404(self):
        response = self.client.get(reverse("employee_detail", args=[99999999]))
        self.assertEqual(response.status_code, 404)
