from datetime import date

from django.urls import reverse
from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity
from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import (
    activity_factory,
    attendance_record_factory,
    employee_factory,
)


class AttendanceEditDeleteTestMixin:
    def _login_as_plain_user(self, *, first_name="NoPerm", emp_code):
        employee = employee_factory(first_name=first_name, emp_code=emp_code)
        user = employee.user
        user.set_password(TEST_PASSWORD)
        user.save()
        self.login_as(user=user)
        return user


class AttendanceActivityEditDeleteTests(
    AttendanceEditDeleteTestMixin, BaseTenantTestCase
):
    def test_edit_get_200(self):
        punch = activity_factory(external_id="TX-ED-GET")

        response = self.client.get(reverse("transaction_edit", args=[punch.pk]))

        self.assertEqual(response.status_code, 200)

    def test_edit_post_updates_and_triggers(self):
        punch = activity_factory(
            external_id="TX-ED-POST",
            direction=AttendanceActivity.Direction.IN,
        )
        punch_time = timezone.now().strftime("%Y-%m-%dT%H:%M")

        response = self.client.post(
            reverse("transaction_edit", args=[punch.pk]),
            {
                "employee": punch.employee.pk,
                "punch_time": punch_time,
                "direction": "out",
                "method": "manual",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "transactionUpdated")
        punch.refresh_from_db()
        self.assertEqual(punch.direction, AttendanceActivity.Direction.OUT)
        self.assertEqual(punch.external_id, "TX-ED-POST")

    def test_delete_soft_deletes_and_triggers(self):
        punch = activity_factory(external_id="TX-ED-DEL")

        response = self.client.delete(reverse("transaction_delete", args=[punch.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "transactionDeleted")
        self.assertFalse(AttendanceActivity.objects.filter(pk=punch.pk).exists())
        self.assertTrue(AttendanceActivity.all_objects.filter(pk=punch.pk).exists())

    def test_delete_without_perm_forbidden(self):
        punch = activity_factory(external_id="TX-ED-403")
        self._login_as_plain_user(emp_code="TX-NOPERM")

        response = self.client.delete(reverse("transaction_delete", args=[punch.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(AttendanceActivity.objects.filter(pk=punch.pk).exists())

    def test_delete_missing_id_404(self):
        response = self.client.delete(reverse("transaction_delete", args=[999999]))

        self.assertEqual(response.status_code, 404)


class AttendanceRecordEditDeleteTests(AttendanceEditDeleteTestMixin, BaseTenantTestCase):
    def test_edit_get_200(self):
        record = attendance_record_factory(day=date(2026, 7, 20))

        response = self.client.get(reverse("daily_edit", args=[record.pk]))

        self.assertEqual(response.status_code, 200)

    def test_edit_post_updates_and_triggers(self):
        record = attendance_record_factory(
            day=date(2026, 7, 21),
            status=Attendance.Status.PRESENT,
        )

        response = self.client.post(
            reverse("daily_edit", args=[record.pk]),
            {
                "employee": record.employee.pk,
                "day": "2026-07-21",
                "status": "late",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "dailyUpdated")
        record.refresh_from_db()
        self.assertEqual(record.status, Attendance.Status.LATE)

    def test_delete_soft_deletes_and_triggers(self):
        record = attendance_record_factory(day=date(2026, 7, 22))

        response = self.client.delete(reverse("daily_delete", args=[record.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "dailyDeleted")
        self.assertFalse(Attendance.objects.filter(pk=record.pk).exists())
        self.assertTrue(Attendance.all_objects.filter(pk=record.pk).exists())

    def test_delete_without_perm_forbidden(self):
        record = attendance_record_factory(day=date(2026, 7, 23))
        self._login_as_plain_user(emp_code="DA-NOPERM")

        response = self.client.delete(reverse("daily_delete", args=[record.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Attendance.objects.filter(pk=record.pk).exists())

    def test_delete_missing_id_404(self):
        response = self.client.delete(reverse("daily_delete", args=[999999]))

        self.assertEqual(response.status_code, 404)
