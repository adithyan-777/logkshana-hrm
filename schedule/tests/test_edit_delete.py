from datetime import date
from uuid import uuid4

from django.urls import reverse
from django_tenants.utils import get_public_schema_name, schema_context

from common.tests.base import TEST_PASSWORD, BaseTenantTestCase
from common.tests.factories import (
    assignment_dates,
    employee_factory,
    shift_factory,
    timetable_factory,
)
from schedule.forms import build_shift_day_formset
from schedule.models import (
    ScheduleAssignment,
    Shift,
    ShiftDay,
    TemporarySchedule,
    Timetable,
)
from schedule.services import schedule_assignment_create, temporary_schedule_create
from users.models import TenantUser


def make_plain_user(test_case, *, email, username):
    with schema_context(get_public_schema_name()):
        user = TenantUser.objects.create_user(
            email=email,
            username=username,
            password=TEST_PASSWORD,
            is_active=True,
        )
    user.tenants.add(test_case.tenant)
    return user


def timetable_post_data(timetable, **overrides):
    data = {
        "name": "Updated Timetable",
        "code": timetable.code,
        "type": "normal",
        "work_type": "work",
        "workday": "1",
        "check_in": "09:00",
        "check_out": "18:00",
        "check_in_cross_days": "0",
        "check_out_cross_days": "0",
        "late_in_grace_minutes": "0",
        "early_out_grace_minutes": "0",
        "day_change_time": "08:00",
        "require_check_in": "on",
        "require_check_out": "on",
        "is_active": "on",
    }
    data.update(overrides)
    return data


class TimetableEditDeleteTests(BaseTenantTestCase):
    def test_edit_get_200(self):
        timetable = timetable_factory(name="Morning", code=f"TT-{uuid4().hex[:6]}")
        response = self.client.get(reverse("timetable_edit", args=[timetable.pk]))
        self.assertEqual(response.status_code, 200)

    def test_edit_post_updates_and_triggers(self):
        timetable = timetable_factory(name="Morning", code=f"TT-{uuid4().hex[:6]}")
        response = self.client.post(
            reverse("timetable_edit", args=[timetable.pk]),
            timetable_post_data(timetable, name="Evening Updated"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "timetableUpdated")
        timetable.refresh_from_db()
        self.assertEqual(timetable.name, "Evening Updated")

    def test_delete_soft_deletes_and_triggers(self):
        timetable = timetable_factory(name="Morning", code=f"TT-{uuid4().hex[:6]}")
        response = self.client.delete(reverse("timetable_delete", args=[timetable.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "timetableDeleted")
        self.assertFalse(Timetable.objects.filter(pk=timetable.pk).exists())
        self.assertTrue(Timetable.all_objects.filter(pk=timetable.pk).exists())

    def test_delete_without_perm_403(self):
        timetable = timetable_factory(name="Morning", code=f"TT-{uuid4().hex[:6]}")
        plain = make_plain_user(
            self,
            email=f"plain_tt_{uuid4().hex[:6]}@example.com",
            username=f"plain_tt_{uuid4().hex[:6]}",
        )
        self.login_as(user=plain)
        response = self.client.delete(reverse("timetable_delete", args=[timetable.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Timetable.objects.filter(pk=timetable.pk).exists())

    def test_delete_missing_404(self):
        response = self.client.delete(reverse("timetable_delete", args=[999999]))
        self.assertEqual(response.status_code, 404)


class ShiftEditDeleteTests(BaseTenantTestCase):
    def _shift_post_data(self, shift, day, new_timetable, **overrides):
        formset = build_shift_day_formset(instance=shift)
        prefix = formset.prefix
        data = {
            "name": "Updated Shift",
            "code": shift.code,
            "cycle_unit": "week",
            "cycle_count": "1",
            "is_active": "on",
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "1",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            f"{prefix}-0-id": str(day.pk),
            f"{prefix}-0-day_number": "1",
            f"{prefix}-0-timetable": str(new_timetable.pk),
        }
        data.update(overrides)
        return data

    def test_edit_get_200(self):
        shift = shift_factory(name="Week", code=f"SH-{uuid4().hex[:6]}")
        response = self.client.get(reverse("shift_edit", args=[shift.pk]))
        self.assertEqual(response.status_code, 200)

    def test_edit_post_updates_and_triggers(self):
        shift = shift_factory(name="Week", code=f"SH-{uuid4().hex[:6]}")
        day = shift.days.get()
        new_timetable = timetable_factory(name="Evening", code=f"EV-{uuid4().hex[:6]}")
        response = self.client.post(
            reverse("shift_edit", args=[shift.pk]),
            self._shift_post_data(shift, day, new_timetable),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "shiftUpdated")
        shift.refresh_from_db()
        self.assertEqual(shift.name, "Updated Shift")
        self.assertEqual(shift.days.count(), 1)
        self.assertEqual(shift.days.get().timetable_id, new_timetable.pk)

    def test_edit_post_removing_day_soft_deletes_it(self):
        shift = shift_factory(name="Week", code=f"SH-{uuid4().hex[:6]}")
        day = shift.days.get()
        formset = build_shift_day_formset(instance=shift)
        prefix = formset.prefix
        response = self.client.post(
            reverse("shift_edit", args=[shift.pk]),
            {
                "name": shift.name,
                "code": shift.code,
                "cycle_unit": "week",
                "cycle_count": "1",
                "is_active": "on",
                f"{prefix}-TOTAL_FORMS": "1",
                f"{prefix}-INITIAL_FORMS": "1",
                f"{prefix}-MIN_NUM_FORMS": "0",
                f"{prefix}-MAX_NUM_FORMS": "1000",
                f"{prefix}-0-id": str(day.pk),
                f"{prefix}-0-day_number": "1",
                f"{prefix}-0-timetable": str(day.timetable_id),
                f"{prefix}-0-DELETE": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "shiftUpdated")
        self.assertEqual(shift.days.count(), 0)
        self.assertFalse(ShiftDay.objects.filter(pk=day.pk).exists())
        self.assertTrue(ShiftDay.all_objects.filter(pk=day.pk).exists())

    def test_delete_soft_deletes_shift_and_days(self):
        shift = shift_factory(name="Week", code=f"SH-{uuid4().hex[:6]}")
        day_pk = shift.days.get().pk
        response = self.client.delete(reverse("shift_delete", args=[shift.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "shiftDeleted")
        self.assertFalse(Shift.objects.filter(pk=shift.pk).exists())
        self.assertTrue(Shift.all_objects.filter(pk=shift.pk).exists())
        self.assertFalse(ShiftDay.objects.filter(pk=day_pk).exists())
        self.assertTrue(ShiftDay.all_objects.filter(pk=day_pk).exists())

    def test_delete_without_perm_403(self):
        shift = shift_factory(name="Week", code=f"SH-{uuid4().hex[:6]}")
        plain = make_plain_user(
            self,
            email=f"plain_sh_{uuid4().hex[:6]}@example.com",
            username=f"plain_sh_{uuid4().hex[:6]}",
        )
        self.login_as(user=plain)
        response = self.client.delete(reverse("shift_delete", args=[shift.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Shift.objects.filter(pk=shift.pk).exists())

    def test_delete_missing_404(self):
        response = self.client.delete(reverse("shift_delete", args=[999999]))
        self.assertEqual(response.status_code, 404)


class AssignmentEditDeleteTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.shift = shift_factory(name="Week", code=f"SH-{uuid4().hex[:6]}")
        self.employee = employee_factory(
            first_name="Assign", emp_code=f"EA-{uuid4().hex[:6]}"
        )
        self.start_date, self.end_date = assignment_dates()
        self.assignment = schedule_assignment_create(
            assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
            shift=self.shift,
            start_date=self.start_date,
            end_date=self.end_date,
            employee=self.employee,
        )

    def _post_data(self, **overrides):
        data = {
            "assignment_type": "employee",
            "shift": str(self.shift.pk),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "employee": str(self.employee.pk),
            "department": "",
        }
        data.update(overrides)
        return data

    def test_edit_get_200(self):
        response = self.client.get(
            reverse("assignment_edit", args=[self.assignment.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_edit_post_updates_and_triggers(self):
        new_end = date(2026, 6, 30)
        response = self.client.post(
            reverse("assignment_edit", args=[self.assignment.pk]),
            self._post_data(end_date=new_end.isoformat()),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "assignmentUpdated")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.end_date, new_end)

    def test_delete_soft_deletes_and_triggers(self):
        response = self.client.delete(
            reverse("assignment_delete", args=[self.assignment.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "assignmentDeleted")
        self.assertFalse(
            ScheduleAssignment.objects.filter(pk=self.assignment.pk).exists()
        )
        self.assertTrue(
            ScheduleAssignment.all_objects.filter(pk=self.assignment.pk).exists()
        )

    def test_delete_without_perm_403(self):
        plain = make_plain_user(
            self,
            email=f"plain_as_{uuid4().hex[:6]}@example.com",
            username=f"plain_as_{uuid4().hex[:6]}",
        )
        self.login_as(user=plain)
        response = self.client.delete(
            reverse("assignment_delete", args=[self.assignment.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            ScheduleAssignment.objects.filter(pk=self.assignment.pk).exists()
        )

    def test_delete_missing_404(self):
        response = self.client.delete(reverse("assignment_delete", args=[999999]))
        self.assertEqual(response.status_code, 404)


class TemporaryEditDeleteTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        self.employee = employee_factory(
            first_name="Temp", emp_code=f"ET-{uuid4().hex[:6]}"
        )
        self.timetable = timetable_factory(
            name="Overtime", code=f"OT-{uuid4().hex[:6]}"
        )
        self.temporary = temporary_schedule_create(
            employee=self.employee,
            date=date(2026, 6, 1),
            timetable=self.timetable,
            reason="Weekend work",
        )

    def _post_data(self, **overrides):
        data = {
            "employee": str(self.employee.pk),
            "date": "2026-06-01",
            "timetable": str(self.timetable.pk),
            "reason": "Updated reason",
            "overrides_normal_schedule": "on",
        }
        data.update(overrides)
        return data

    def test_edit_get_200(self):
        response = self.client.get(reverse("temporary_edit", args=[self.temporary.pk]))
        self.assertEqual(response.status_code, 200)

    def test_edit_post_updates_and_triggers(self):
        response = self.client.post(
            reverse("temporary_edit", args=[self.temporary.pk]),
            self._post_data(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "temporaryUpdated")
        self.temporary.refresh_from_db()
        self.assertEqual(self.temporary.reason, "Updated reason")

    def test_delete_soft_deletes_and_triggers(self):
        response = self.client.delete(
            reverse("temporary_delete", args=[self.temporary.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "temporaryDeleted")
        self.assertFalse(
            TemporarySchedule.objects.filter(pk=self.temporary.pk).exists()
        )
        self.assertTrue(
            TemporarySchedule.all_objects.filter(pk=self.temporary.pk).exists()
        )

    def test_delete_without_perm_403(self):
        plain = make_plain_user(
            self,
            email=f"plain_tp_{uuid4().hex[:6]}@example.com",
            username=f"plain_tp_{uuid4().hex[:6]}",
        )
        self.login_as(user=plain)
        response = self.client.delete(
            reverse("temporary_delete", args=[self.temporary.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(TemporarySchedule.objects.filter(pk=self.temporary.pk).exists())

    def test_delete_missing_404(self):
        response = self.client.delete(reverse("temporary_delete", args=[999999]))
        self.assertEqual(response.status_code, 404)
