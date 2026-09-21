from datetime import date
from uuid import uuid4

from django.urls import reverse
from django_tenants.utils import get_public_schema_name, schema_context

from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from leave.models import Holiday, LeavePolicy, LeaveRequest, LeaveType
from leave.services import (
    holiday_create,
    leave_policy_create,
    leave_request_create,
    leave_type_create,
)


def _make_plain_user(testcase):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    suffix = uuid4().hex[:8]
    with schema_context(get_public_schema_name()):
        user = User.objects.create_user(
            email=f"plain_{suffix}@example.com",
            username=f"plain_{suffix}",
            password=TEST_PASSWORD,
            is_active=True,
        )
    user.tenants.add(testcase.tenant)
    from tenant_users.permissions.models import UserTenantPermissions

    UserTenantPermissions.objects.update_or_create(
        profile=user,
        defaults={"is_staff": False, "is_superuser": False},
    )
    return user


def _leave_type(**kwargs):
    kwargs.setdefault("name", f"LT-{uuid4().hex[:6]}")
    kwargs.setdefault("code", f"C-{uuid4().hex[:6]}")
    return leave_type_create(**kwargs)


def _employee(**kwargs):
    from employees.services import employee_create

    kwargs.setdefault("first_name", "Test")
    kwargs.setdefault("emp_code", f"E-{uuid4().hex[:6]}")
    kwargs.setdefault("mobile", f"+97433{uuid4().hex[:6]}")
    return employee_create(**kwargs)


def _leave_policy(**kwargs):
    if "leave_type" not in kwargs:
        kwargs["leave_type"] = _leave_type()
    kwargs.setdefault("name", f"Pol-{uuid4().hex[:6]}")
    kwargs.setdefault("accrual_type", LeavePolicy.AccrualType.YEARLY)
    return leave_policy_create(**kwargs)


def _leave_request(**kwargs):
    if "employee" not in kwargs:
        kwargs["employee"] = _employee()
    if "leave_type" not in kwargs:
        kwargs["leave_type"] = _leave_type()
    kwargs.setdefault("start_date", date(2026, 3, 1))
    kwargs.setdefault("end_date", date(2026, 3, 3))
    kwargs.setdefault("duration_type", LeaveRequest.DurationType.FULL_DAY)
    kwargs.setdefault("days", 3)
    kwargs.setdefault("status", LeaveRequest.Status.PENDING)
    return leave_request_create(**kwargs)


def _holiday(**kwargs):
    kwargs.setdefault("name", f"Hol-{uuid4().hex[:6]}")
    kwargs.setdefault("date", date(2026, 1, 1))
    kwargs.setdefault("holiday_type", Holiday.HolidayType.PUBLIC)
    return holiday_create(**kwargs)


class LeaveTypeEditDeleteTests(BaseTenantTestCase):
    def test_edit_get_redirects_to_list_drawer(self):
        lt = _leave_type()
        response = self.client.get(reverse("leave_type_edit", args=[lt.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("leave_type_list"), response.url)
        self.assertIn("drawer=", response.url)

    def test_edit_post_updates_and_trigger(self):
        lt = _leave_type(name="Before")
        response = self.client.post(
            reverse("leave_type_edit", args=[lt.pk]),
            {
                "name": "After",
                "code": lt.code,
                "description": "updated",
                "paid": "on",
                "requires_approval": "on",
                "allow_half_day": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "leaveTypeUpdated")
        lt.refresh_from_db()
        self.assertEqual(lt.name, "After")

    def test_delete_soft_deletes_and_trigger(self):
        lt = _leave_type()
        response = self.client.delete(reverse("leave_type_delete", args=[lt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "leaveTypeDeleted")
        self.assertFalse(LeaveType.objects.filter(pk=lt.pk).exists())
        self.assertTrue(LeaveType.all_objects.filter(pk=lt.pk).exists())

    def test_delete_without_perm_403(self):
        lt = _leave_type()
        plain = _make_plain_user(self)
        self.login_as(user=plain)
        response = self.client.delete(reverse("leave_type_delete", args=[lt.pk]))
        self.assertEqual(response.status_code, 403)

    def test_delete_missing_404(self):
        response = self.client.delete(reverse("leave_type_delete", args=[999999]))
        self.assertEqual(response.status_code, 404)


class LeavePolicyEditDeleteTests(BaseTenantTestCase):
    def test_edit_get_redirects_to_list_drawer(self):
        policy = _leave_policy()
        response = self.client.get(reverse("leave_policy_edit", args=[policy.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("leave_policy_list"), response.url)
        self.assertIn("drawer=", response.url)

    def test_edit_post_updates_and_trigger(self):
        policy = _leave_policy(name="PolBefore")
        response = self.client.post(
            reverse("leave_policy_edit", args=[policy.pk]),
            {
                "leave_type": policy.leave_type.pk,
                "name": "PolAfter",
                "entitlement_days": "30",
                "accrual_type": "yearly",
                "accrual_days": "0",
                "minimum_service_days": "0",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "leavePolicyUpdated")
        policy.refresh_from_db()
        self.assertEqual(policy.name, "PolAfter")

    def test_delete_soft_deletes_and_trigger(self):
        policy = _leave_policy()
        response = self.client.delete(reverse("leave_policy_delete", args=[policy.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "leavePolicyDeleted")
        self.assertFalse(LeavePolicy.objects.filter(pk=policy.pk).exists())
        self.assertTrue(LeavePolicy.all_objects.filter(pk=policy.pk).exists())

    def test_delete_without_perm_403(self):
        policy = _leave_policy()
        plain = _make_plain_user(self)
        self.login_as(user=plain)
        response = self.client.delete(reverse("leave_policy_delete", args=[policy.pk]))
        self.assertEqual(response.status_code, 403)

    def test_delete_missing_404(self):
        response = self.client.delete(reverse("leave_policy_delete", args=[999999]))
        self.assertEqual(response.status_code, 404)


class LeaveRequestEditDeleteTests(BaseTenantTestCase):
    def test_edit_get_redirects_to_list_drawer(self):
        lr = _leave_request()
        response = self.client.get(reverse("leave_request_edit", args=[lr.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("leave_request_list"), response.url)
        self.assertIn("drawer=", response.url)

    def test_edit_post_updates_and_trigger(self):
        lr = _leave_request()
        response = self.client.post(
            reverse("leave_request_edit", args=[lr.pk]),
            {
                "employee": lr.employee.pk,
                "leave_type": lr.leave_type.pk,
                "start_date": "2026-03-01",
                "end_date": "2026-03-03",
                "duration_type": "full_day",
                "days": "3",
                "status": "pending",
                "reason": "Updated reason",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "leaveRequestUpdated")
        lr.refresh_from_db()
        self.assertEqual(lr.reason, "Updated reason")

    def test_delete_soft_deletes_and_trigger(self):
        lr = _leave_request()
        response = self.client.delete(reverse("leave_request_delete", args=[lr.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "leaveRequestDeleted")
        self.assertFalse(LeaveRequest.objects.filter(pk=lr.pk).exists())
        self.assertTrue(LeaveRequest.all_objects.filter(pk=lr.pk).exists())

    def test_delete_without_perm_403(self):
        lr = _leave_request()
        plain = _make_plain_user(self)
        self.login_as(user=plain)
        response = self.client.delete(reverse("leave_request_delete", args=[lr.pk]))
        self.assertEqual(response.status_code, 403)

    def test_delete_missing_404(self):
        response = self.client.delete(reverse("leave_request_delete", args=[999999]))
        self.assertEqual(response.status_code, 404)


class HolidayEditDeleteTests(BaseTenantTestCase):
    def test_edit_get_redirects_to_list_drawer(self):
        h = _holiday()
        response = self.client.get(reverse("holiday_edit", args=[h.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("holiday_list"), response.url)
        self.assertIn("drawer=", response.url)

    def test_edit_post_updates_and_trigger(self):
        h = _holiday()
        response = self.client.post(
            reverse("holiday_edit", args=[h.pk]),
            {
                "name": "HolAfter",
                "date": "2026-01-01",
                "holiday_type": "public",
                "description": "updated",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "holidayUpdated")
        h.refresh_from_db()
        self.assertEqual(h.name, "HolAfter")

    def test_delete_soft_deletes_and_trigger(self):
        h = _holiday()
        response = self.client.delete(reverse("holiday_delete", args=[h.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "holidayDeleted")
        self.assertFalse(Holiday.objects.filter(pk=h.pk).exists())
        self.assertTrue(Holiday.all_objects.filter(pk=h.pk).exists())

    def test_delete_without_perm_403(self):
        h = _holiday()
        plain = _make_plain_user(self)
        self.login_as(user=plain)
        response = self.client.delete(reverse("holiday_delete", args=[h.pk]))
        self.assertEqual(response.status_code, 403)

    def test_delete_missing_404(self):
        response = self.client.delete(reverse("holiday_delete", args=[999999]))
        self.assertEqual(response.status_code, 404)
