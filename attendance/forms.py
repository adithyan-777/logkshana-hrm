from django import forms

from employees.models import Employee
from schedule.models import Shift, Timetable
from attendance.models import (
    AttendanceCorrection,
    AttendanceRule,
    AttendanceTransaction,
    DailyAttendance,
)

DATE_INPUT = forms.DateInput(attrs={"type": "date"})
DATETIME_INPUT = forms.DateTimeInput(
    attrs={"type": "datetime-local"},
    format="%Y-%m-%dT%H:%M",
)


class AttendanceTransactionForm(forms.ModelForm):
    class Meta:
        model = AttendanceTransaction
        fields = [
            "employee",
            "timestamp",
            "direction",
            "source",
        ]
        widgets = {
            "timestamp": DATETIME_INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("first_name", "last_name")


class DailyAttendanceForm(forms.ModelForm):
    class Meta:
        model = DailyAttendance
        fields = [
            "employee",
            "date",
            "status",
            "shift",
            "timetable",
            "scheduled_minutes",
            "worked_minutes",
            "late_minutes",
            "early_leave_minutes",
            "overtime_minutes",
            "has_check_in",
            "has_check_out",
            "notes",
        ]
        widgets = {
            "date": DATE_INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("first_name", "last_name")
        self.fields["shift"].queryset = Shift.objects.filter(is_active=True).order_by(
            "name"
        )
        self.fields["timetable"].queryset = Timetable.objects.filter(
            is_active=True
        ).order_by("name")


class AttendanceCorrectionForm(forms.ModelForm):
    class Meta:
        model = AttendanceCorrection
        fields = [
            "employee",
            "date",
            "check_in",
            "check_out",
            "reason",
            "status",
        ]
        widgets = {
            "date": DATE_INPUT,
            "check_in": DATETIME_INPUT,
            "check_out": DATETIME_INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("first_name", "last_name")

    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get("check_in")
        check_out = cleaned_data.get("check_out")

        if check_in and check_out and check_out < check_in:
            self.add_error("check_out", "Check-out must be on or after check-in.")

        return cleaned_data


class AttendanceRuleForm(forms.ModelForm):
    class Meta:
        model = AttendanceRule
        fields = [
            "name",
            "require_check_in",
            "require_check_out",
            "missing_check_in_as_absence",
            "missing_check_out_as_incomplete",
            "late_grace_minutes",
            "early_leave_grace_minutes",
            "late_to_absence_minutes",
            "duplicate_punch_window_minutes",
            "allow_multiple_in_out",
            "is_active",
        ]
