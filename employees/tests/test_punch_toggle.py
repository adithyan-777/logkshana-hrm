from django.contrib.auth import get_user_model
from django.urls import reverse
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.models import AttendanceActivity
from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import activity_factory, employee_factory
from employees.models import EmployeePunchStatus

User = get_user_model()


def _plain_user(*, username: str, tenant=None) -> User:
    """A non-staff user with no tenant permissions, in the public schema.

    Optional ``tenant`` membership: the CompanyMembershipMiddleware is
    the *outer* gate — a logged-in non-member gets 404 on any tenant
    page before permission checks even run — so the permission tests
    need a membership-yes / permission-no user.
    """
    with schema_context(get_public_schema_name()):
        user = User.objects.create_user(username=username, password=TEST_PASSWORD)
        user.set_password(TEST_PASSWORD)
        user.save(update_fields=["password"])
        if tenant is not None:
            tenant.add_user(user)
        return user


class EmployeePunchToggleTests(BaseTenantTestCase):
    """One-click web punch: inverse-direction, permission, badge swap."""

    def test_punched_out_gets_punched_in(self):
        employee = employee_factory(first_name="Toggle", emp_code="PT100")

        response = self.client.post(
            reverse("employee_punch_toggle", args=[employee.pk])
        )

        employee.refresh_from_db()
        self.assertEqual(
            employee.punch_status, EmployeePunchStatus.CHECK_IN
        )
        activity = AttendanceActivity.objects.order_by("-id").first()
        self.assertEqual(activity.direction, AttendanceActivity.Direction.IN)
        self.assertEqual(
            activity.method,
            AttendanceActivity.AttendanceActivityMethodType.WEB,
        )
        self.assertContains(response, "checked in")

    def test_punched_in_gets_punched_out(self):
        employee = employee_factory(first_name="Toggle", emp_code="PT101")
        activity_factory(
            employee=employee,
            direction=AttendanceActivity.Direction.IN,
        )

        response = self.client.post(
            reverse("employee_punch_toggle", args=[employee.pk])
        )

        employee.refresh_from_db()
        self.assertEqual(
            employee.punch_status, EmployeePunchStatus.CHECK_OUT
        )
        self.assertContains(response, "checked out")

    def test_sub_periods_close_first(self):
        employee = employee_factory(first_name="Toggle", emp_code="PT102")
        for direction in (
            AttendanceActivity.Direction.IN,
            AttendanceActivity.Direction.BREAK_IN,
        ):
            activity_factory(employee=employee, direction=direction)
        employee.refresh_from_db()
        self.assertEqual(
            employee.punch_status, EmployeePunchStatus.BREAK_IN
        )

        self.client.post(reverse("employee_punch_toggle", args=[employee.pk]))
        employee.refresh_from_db()
        # A click while on break ends the break (returns to work), a
        # click when back from break / on overtime-out closes the day.
        self.assertEqual(
            employee.punch_status, EmployeePunchStatus.BREAK_OUT
        )
        self.assertEqual(
            employee.next_punch_direction, AttendanceActivity.Direction.OUT
        )

    def test_overtime_toggles_its_own_period(self):
        employee = employee_factory(first_name="Toggle", emp_code="PT103")
        for direction in (
            AttendanceActivity.Direction.IN,
            AttendanceActivity.Direction.OUT,
            AttendanceActivity.Direction.OVERTIME_IN,
        ):
            activity_factory(employee=employee, direction=direction)

        self.client.post(reverse("employee_punch_toggle", args=[employee.pk]))
        employee.refresh_from_db()
        self.assertEqual(
            employee.punch_status, EmployeePunchStatus.OVERTIME_OUT
        )

    def test_without_permission_is_denied(self):
        employee = employee_factory(first_name="No PB", emp_code="PT104")

        # Fresh non-staff user: no tenant permission at all. The shared
        # user must be created in the public schema and logged in on
        # the SAME tenant client (a second client mid-class breaks the
        # tenant context harness relies on).
        user = _plain_user(username="plain_toggle", tenant=self.tenant)
        self.login_as(user=user, via="username")
        response = self.client.post(
            reverse("employee_punch_toggle", args=[employee.pk])
        )

        self.assertEqual(response.status_code, 403)
        employee.refresh_from_db()
        self.assertEqual(employee.punch_status, "")
        self.assertFalse(
            AttendanceActivity.objects.filter(employee=employee).exists()
        )

    def test_get_is_not_allowed(self):
        employee = employee_factory(first_name="No GET", emp_code="PT105")

        response = self.client.get(
            reverse("employee_punch_toggle", args=[employee.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_list_shows_button_for_permission_holder(self):
        employee = employee_factory(first_name="Admin", emp_code="PT106")

        response = self.client.get(reverse("employee_list"))

        self.assertContains(response, "badge hover-swap")
        self.assertContains(
            response,
            reverse("employee_punch_toggle", args=[employee.pk]),
        )

    def test_list_shows_plain_badge_without_permission(self):
        user = _plain_user(username="plain_badge", tenant=self.tenant)
        # Member who may view employees (sees the list) but lacks
        # attendance.add: the badge must render without any toggle.
        from employees.models import Permission as _Perm
        from employees.models import Role

        permission, _ = _Perm.objects.get_or_create(
            codename="employees.view",
            defaults={"name": "View employees"},
        )
        role = Role.objects.create(name="Site Viewer")
        role.permissions.add(permission)
        employee = employee_factory(
            first_name="Plain", emp_code="PT107"
        )
        activity_factory(
            employee=employee,
            direction=AttendanceActivity.Direction.IN,
        )
        employee.user = user
        # employee_create forces the base "Employee" role; override it
        # afterwards so the user holds employees.view only.
        employee.role = role
        employee.save(update_fields=["user", "role"])

        self.login_as(user=user, via="username")
        response = self.client.get(reverse("employee_list"))

        self.assertContains(response, "badge punch-in")
        self.assertNotContains(response, "badge hover-swap")
        self.assertNotContains(
            response,
            reverse("employee_punch_toggle", args=[employee.pk]),
        )

        self.assertContains(response, "badge punch-in")
        self.assertNotContains(response, "badge hover-swap")
        self.assertNotContains(
            response,
            reverse("employee_punch_toggle", args=[employee.pk]),
        )
