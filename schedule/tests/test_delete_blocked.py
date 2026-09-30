import json
from datetime import date

from django.urls import reverse

from common.tests.base import BaseTenantTestCase
from common.tests.factories import (
    employee_factory,
    schedule_factory,
    timetable_factory,
)
from schedule.models import EmployeeScheduleAssignment, Schedule


class DeleteBlockedTests(BaseTenantTestCase):
    def setUp(self):
        super().setUp()
        employee = employee_factory(first_name="Roster", emp_code="DB001")
        self.timetable = timetable_factory(name="Morning", code="MORN-DB")
        self.schedule = schedule_factory(name="Weekly", timetable=self.timetable)
        assignment = EmployeeScheduleAssignment.objects.create(
            schedule=self.schedule,
            start_date=date(2026, 1, 1),
            priority=0,
        )
        assignment.employees.add(employee)

    def test_schedule_delete_blocked_by_assignment(self):
        response = self.client.delete(
            reverse("schedule_delete", args=[self.schedule.pk])
        )

        self.assertEqual(response.status_code, 200)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["showToast"]["type"], "error")
        self.assertNotIn("scheduleDeleted", trigger)
        self.assertTrue(Schedule.objects.filter(pk=self.schedule.pk).exists())

    def test_timetable_delete_blocked_by_assignment(self):
        response = self.client.delete(
            reverse("timetable_delete", args=[self.timetable.pk])
        )

        self.assertEqual(response.status_code, 200)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["showToast"]["type"], "error")
        self.assertNotIn("timetableDeleted", trigger)
        self.assertTrue(Schedule.objects.filter(pk=self.schedule.pk).exists())
