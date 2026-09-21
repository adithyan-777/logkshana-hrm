from common.tests.base import BaseTenantTestCase
from schedule.forms import TimetableForm


def timetable_form_data(**overrides) -> dict:
    data = {
        "name": "Night Shift",
        "code": "NIGHT",
        "type": "normal",
        "work_type": "work",
        "workday": "1",
        "check_in": "22:00",
        "check_out": "06:00",
        "check_in_start": "",
        "check_in_end": "",
        "check_out_start": "",
        "check_out_end": "",
        "check_in_cross_days": "0",
        "check_out_cross_days": "1",
        "require_check_in": "on",
        "require_check_out": "on",
        "allow_late_in": "",
        "allow_early_out": "",
        "late_in_grace_minutes": "0",
        "early_out_grace_minutes": "0",
        "multiple_in_out": "",
        "day_change_time": "08:00",
        "color": "#14b8a6",
        "is_active": "on",
        "work_hours": "8",
        "work_mins": "0",
    }
    data.update(overrides)
    return data


class TimetableFormCrossDayTests(BaseTenantTestCase):
    def test_overnight_shift_without_cross_days_is_rejected(self):
        form = TimetableForm(data=timetable_form_data(check_out_cross_days="0"))

        self.assertFalse(form.is_valid())
        self.assertIn("check_out_cross_days", form.errors)

    def test_overnight_shift_with_cross_day_is_valid(self):
        form = TimetableForm(data=timetable_form_data())

        self.assertTrue(form.is_valid(), form.errors)

    def test_cross_day_toggle_forces_overnight_offset(self):
        form = TimetableForm(
            data=timetable_form_data(cross_day="on", check_out_cross_days="0")
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["check_out_cross_days"], 1)

    def test_zero_length_shift_is_rejected(self):
        form = TimetableForm(
            data=timetable_form_data(
                code="ZERO",
                check_in="09:00",
                check_out="09:00",
                check_out_cross_days="0",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("check_out_cross_days", form.errors)

    def test_same_day_shift_is_valid(self):
        form = TimetableForm(
            data=timetable_form_data(
                code="DAY",
                check_in="09:00",
                check_out="18:00",
                check_out_cross_days="0",
            )
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_flexible_requires_work_hours(self):
        form = TimetableForm(
            data=timetable_form_data(
                code="FLEX",
                type="flexible",
                check_in="09:00",
                check_out="18:00",
                check_out_cross_days="0",
                work_hours="",
                work_mins="",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("work_hours", form.errors)

    def test_break_payload_in_service_kwargs(self):
        form = TimetableForm(
            data=timetable_form_data(
                code="BRK",
                check_in="09:00",
                check_out="18:00",
                check_out_cross_days="0",
                enable_break="on",
                break_start="12:00",
                break_end="13:00",
                break_duration="60",
                count_break_as_work="on",
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        payload = form.service_kwargs()
        self.assertIsNotNone(payload["break_data"])
        self.assertEqual(str(payload["break_data"]["start_time"]), "12:00:00")
        self.assertTrue(payload["break_data"]["paid"])

    def test_auto_code_from_name(self):
        form = TimetableForm(
            data=timetable_form_data(
                name="Morning Shift",
                code="",
                check_in="09:00",
                check_out="18:00",
                check_out_cross_days="0",
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["code"], "MORNING-SHIFT")
