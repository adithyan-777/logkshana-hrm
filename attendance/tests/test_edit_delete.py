from datetime import date

from django.urls import reverse
from django.utils import timezone

from attendance.models import (
    AttendanceCorrection,
    AttendanceRule,
    AttendanceTransaction,
    DailyAttendance,
)
from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import (
    attendance_correction_factory,
    attendance_rule_factory,
    attendance_transaction_factory,
    daily_attendance_factory,
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


class AttendanceTransactionEditDeleteTests(
    AttendanceEditDeleteTestMixin, BaseTenantTestCase
):
    def test_edit_get_redirects_to_list_drawer(self):
        punch = attendance_transaction_factory(external_id="TX-ED-GET")

        response = self.client.get(reverse("transaction_edit", args=[punch.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("attendance_transaction_list"), response.url)
        self.assertIn("drawer=", response.url)

    def test_edit_post_updates_and_triggers(self):
        punch = attendance_transaction_factory(
            external_id="TX-ED-POST",
            direction=AttendanceTransaction.Direction.IN,
        )
        timestamp = timezone.now().strftime("%Y-%m-%dT%H:%M")

        response = self.client.post(
            reverse("transaction_edit", args=[punch.pk]),
            {
                "employee": punch.employee.pk,
                "timestamp": timestamp,
                "direction": "out",
                "source": "manual",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "transactionUpdated")
        punch.refresh_from_db()
        self.assertEqual(punch.direction, AttendanceTransaction.Direction.OUT)
        self.assertEqual(punch.external_id, "TX-ED-POST")
        self.assertEqual(punch.external_employee_id, punch.employee.emp_code)

    def test_delete_soft_deletes_and_triggers(self):
        punch = attendance_transaction_factory(external_id="TX-ED-DEL")

        response = self.client.delete(reverse("transaction_delete", args=[punch.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "transactionDeleted")
        self.assertFalse(
            AttendanceTransaction.objects.filter(pk=punch.pk).exists()
        )
        self.assertTrue(
            AttendanceTransaction.all_objects.filter(pk=punch.pk).exists()
        )

    def test_delete_without_perm_forbidden(self):
        punch = attendance_transaction_factory(external_id="TX-ED-403")
        self._login_as_plain_user(emp_code="TX-NOPERM")

        response = self.client.delete(reverse("transaction_delete", args=[punch.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            AttendanceTransaction.objects.filter(pk=punch.pk).exists()
        )

    def test_delete_missing_id_404(self):
        response = self.client.delete(reverse("transaction_delete", args=[999999]))

        self.assertEqual(response.status_code, 404)


class DailyAttendanceEditDeleteTests(AttendanceEditDeleteTestMixin, BaseTenantTestCase):
    def test_edit_get_redirects_to_list_drawer(self):
        record = daily_attendance_factory(date=date(2026, 7, 20))

        response = self.client.get(reverse("daily_edit", args=[record.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("daily_attendance_list"), response.url)
        self.assertIn("drawer=", response.url)

    def test_edit_post_updates_and_triggers(self):
        record = daily_attendance_factory(
            date=date(2026, 7, 21),
            status=DailyAttendance.Status.PRESENT,
            worked_minutes=480,
        )

        response = self.client.post(
            reverse("daily_edit", args=[record.pk]),
            {
                "employee": record.employee.pk,
                "date": "2026-07-21",
                "status": "late",
                "scheduled_minutes": "480",
                "worked_minutes": "400",
                "late_minutes": "15",
                "early_leave_minutes": "0",
                "overtime_minutes": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "dailyUpdated")
        record.refresh_from_db()
        self.assertEqual(record.status, DailyAttendance.Status.LATE)
        self.assertEqual(record.worked_minutes, 400)
        self.assertEqual(record.late_minutes, 15)

    def test_delete_soft_deletes_and_triggers(self):
        record = daily_attendance_factory(date=date(2026, 7, 22))

        response = self.client.delete(reverse("daily_delete", args=[record.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "dailyDeleted")
        self.assertFalse(DailyAttendance.objects.filter(pk=record.pk).exists())
        self.assertTrue(DailyAttendance.all_objects.filter(pk=record.pk).exists())

    def test_delete_without_perm_forbidden(self):
        record = daily_attendance_factory(date=date(2026, 7, 23))
        self._login_as_plain_user(emp_code="DA-NOPERM")

        response = self.client.delete(reverse("daily_delete", args=[record.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(DailyAttendance.objects.filter(pk=record.pk).exists())

    def test_delete_missing_id_404(self):
        response = self.client.delete(reverse("daily_delete", args=[999999]))

        self.assertEqual(response.status_code, 404)


class AttendanceCorrectionEditDeleteTests(
    AttendanceEditDeleteTestMixin, BaseTenantTestCase
):
    def test_edit_get_redirects_to_list_drawer(self):
        correction = attendance_correction_factory(reason="Edit GET me")

        response = self.client.get(reverse("correction_edit", args=[correction.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("attendance_correction_list"), response.url)
        self.assertIn("drawer=", response.url)

    def test_edit_post_updates_and_triggers(self):
        correction = attendance_correction_factory(
            date=date(2026, 6, 20),
            reason="Original reason",
        )

        response = self.client.post(
            reverse("correction_edit", args=[correction.pk]),
            {
                "employee": correction.employee.pk,
                "date": "2026-06-20",
                "reason": "Updated reason",
                "status": "approved",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "correctionUpdated")
        correction.refresh_from_db()
        self.assertEqual(correction.reason, "Updated reason")
        self.assertEqual(correction.status, AttendanceCorrection.Status.APPROVED)

    def test_delete_soft_deletes_and_triggers(self):
        correction = attendance_correction_factory(reason="Delete me")

        response = self.client.delete(
            reverse("correction_delete", args=[correction.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "correctionDeleted")
        self.assertFalse(
            AttendanceCorrection.objects.filter(pk=correction.pk).exists()
        )
        self.assertTrue(
            AttendanceCorrection.all_objects.filter(pk=correction.pk).exists()
        )

    def test_delete_without_perm_forbidden(self):
        correction = attendance_correction_factory(reason="Keep me")
        self._login_as_plain_user(emp_code="AC-NOPERM")

        response = self.client.delete(
            reverse("correction_delete", args=[correction.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            AttendanceCorrection.objects.filter(pk=correction.pk).exists()
        )

    def test_delete_missing_id_404(self):
        response = self.client.delete(reverse("correction_delete", args=[999999]))

        self.assertEqual(response.status_code, 404)


class AttendanceRuleEditDeleteTests(AttendanceEditDeleteTestMixin, BaseTenantTestCase):
    def test_edit_get_redirects_to_list_drawer(self):
        rule = attendance_rule_factory(name="Edit GET Rule")

        response = self.client.get(reverse("rule_edit", args=[rule.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("attendance_rule_list"), response.url)
        self.assertIn("drawer=", response.url)

    def test_edit_post_updates_and_triggers(self):
        rule = attendance_rule_factory(name="Edit POST Rule")

        response = self.client.post(
            reverse("rule_edit", args=[rule.pk]),
            {
                "name": "Edited Rule",
                "late_grace_minutes": "20",
                "early_leave_grace_minutes": "5",
                "late_to_absence_minutes": "60",
                "duplicate_punch_window_minutes": "2",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "ruleUpdated")
        rule.refresh_from_db()
        self.assertEqual(rule.name, "Edited Rule")
        self.assertEqual(rule.late_grace_minutes, 20)

    def test_delete_soft_deletes_and_triggers(self):
        rule = attendance_rule_factory(name="Delete Me Rule")

        response = self.client.delete(reverse("rule_delete", args=[rule.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "ruleDeleted")
        self.assertFalse(AttendanceRule.objects.filter(pk=rule.pk).exists())
        self.assertTrue(AttendanceRule.all_objects.filter(pk=rule.pk).exists())

    def test_delete_without_perm_forbidden(self):
        rule = attendance_rule_factory(name="Keep Me Rule")
        self._login_as_plain_user(emp_code="RL-NOPERM")

        response = self.client.delete(reverse("rule_delete", args=[rule.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(AttendanceRule.objects.filter(pk=rule.pk).exists())

    def test_delete_missing_id_404(self):
        response = self.client.delete(reverse("rule_delete", args=[999999]))

        self.assertEqual(response.status_code, 404)
