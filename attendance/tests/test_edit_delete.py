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
    def test_edit_get_redirects_to_list_drawer(self):
        punch = activity_factory(external_id="TX-ED-GET")

        response = self.client.get(reverse("transaction_edit", args=[punch.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("attendance_transaction_list"), response.url)
        self.assertIn("drawer=", response.url)

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
        trigger = response.headers.get("HX-Trigger", "")
        self.assertIn("transactionUpdated", trigger)
        self.assertIn("closeModal", trigger)
        punch.refresh_from_db()
        self.assertEqual(punch.direction, AttendanceActivity.Direction.OUT)
        self.assertEqual(punch.external_id, "TX-ED-POST")

    def test_delete_removes_and_triggers(self):
        punch = activity_factory(external_id="TX-ED-DEL")

        response = self.client.delete(reverse("transaction_delete", args=[punch.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "transactionDeleted")
        self.assertFalse(AttendanceActivity.objects.filter(pk=punch.pk).exists())

    def test_delete_without_perm_forbidden(self):
        punch = activity_factory(external_id="TX-ED-403")
        self._login_as_plain_user(emp_code="TX-NOPERM")

        response = self.client.delete(reverse("transaction_delete", args=[punch.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(AttendanceActivity.objects.filter(pk=punch.pk).exists())

    def test_delete_missing_id_404(self):
        response = self.client.delete(reverse("transaction_delete", args=[999999]))

        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # Gateway (biometric) punches are read-only in the web UI.
    # ------------------------------------------------------------------
    def _biometric_punch(self, *, external_id):
        return activity_factory(
            external_id=external_id,
            method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
        )

    def test_edit_get_biometric_redirects_to_list(self):
        punch = self._biometric_punch(external_id="gateway:ro-edit")

        response = self.client.get(reverse("transaction_edit", args=[punch.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("attendance_transaction_list"), response.url)

    def test_edit_get_biometric_htmx_shows_error_toast(self):
        punch = self._biometric_punch(external_id="gateway:ro-edit-toast")

        response = self.client.get(
            reverse("transaction_edit", args=[punch.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertIn("showToast", response.headers.get("HX-Trigger"))
        self.assertIn("closeModal", response.headers.get("HX-Trigger"))
        punch.refresh_from_db()  # untouched

    def test_edit_post_biometric_blocked(self):
        punch = self._biometric_punch(external_id="gateway:ro-edit-post")
        original_time = punch.punch_time

        response = self.client.post(
            reverse("transaction_edit", args=[punch.pk]),
            {
                "employee": punch.employee.pk,
                "punch_time": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "direction": "out",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("showToast", response.headers.get("HX-Trigger"))
        punch.refresh_from_db()
        self.assertEqual(punch.direction, AttendanceActivity.Direction.IN)
        self.assertEqual(punch.punch_time, original_time)

    def test_delete_biometric_blocked(self):
        punch = self._biometric_punch(external_id="gateway:ro-del")

        response = self.client.delete(reverse("transaction_delete", args=[punch.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("showToast", response.headers.get("HX-Trigger"))
        self.assertTrue(AttendanceActivity.objects.filter(pk=punch.pk).exists())


class AttendanceRecordEditDeleteTests(AttendanceEditDeleteTestMixin, BaseTenantTestCase):
    def test_edit_get_redirects_to_list_drawer(self):
        record = attendance_record_factory(day=date(2026, 7, 20))

        response = self.client.get(reverse("daily_edit", args=[record.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("daily_attendance_list"), response.url)
        self.assertIn("drawer=", response.url)

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

    def test_delete_removes_and_triggers(self):
        record = attendance_record_factory(day=date(2026, 7, 22))

        response = self.client.delete(reverse("daily_delete", args=[record.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "dailyDeleted")
        self.assertFalse(Attendance.objects.filter(pk=record.pk).exists())

    def test_delete_without_perm_forbidden(self):
        record = attendance_record_factory(day=date(2026, 7, 23))
        self._login_as_plain_user(emp_code="DA-NOPERM")

        response = self.client.delete(reverse("daily_delete", args=[record.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Attendance.objects.filter(pk=record.pk).exists())

    def test_delete_missing_id_404(self):
        response = self.client.delete(reverse("daily_delete", args=[999999]))

        self.assertEqual(response.status_code, 404)
