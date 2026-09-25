from django import forms

from attendance.models import Attendance, AttendanceActivity
from common.forms import apply_form_field_ui
from employees.models import Employee
from schedule.models import Timetable

DATE_INPUT = forms.DateInput(attrs={"type": "date"})
DATETIME_INPUT = forms.DateTimeInput(
    attrs={"type": "datetime-local"},
    format="%Y-%m-%dT%H:%M",
)


class AttendanceActivityForm(forms.ModelForm):
    employee_q = forms.CharField(
        required=False,
        label="Employee",
        widget=forms.TextInput(
            attrs={"placeholder": "Type at least 2 letters to search…"}
        ),
    )

    class Meta:
        model = AttendanceActivity
        fields = [
            "employee",
            "punch_time",
            "direction",
            "method",
        ]
        widgets = {
            "employee": forms.HiddenInput,
            "punch_time": DATETIME_INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("first_name", "last_name")
        if self.instance is not None and getattr(self.instance, "employee_id", None):
            emp = self.instance.employee
            self.fields["employee_q"].initial = f"{emp.emp_code} - {emp.full_name}"
        apply_form_field_ui(self)


class AttendanceForm(forms.ModelForm):
    employee_q = forms.CharField(
        required=False,
        label="Employee",
        widget=forms.TextInput(
            attrs={"placeholder": "Type at least 2 letters to search…"}
        ),
    )

    class Meta:
        model = Attendance
        fields = [
            "employee",
            "day",
            "status",
            "shift",
        ]
        widgets = {
            "employee": forms.HiddenInput,
            "day": DATE_INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("first_name", "last_name")
        self.fields["shift"].queryset = Timetable.objects.filter(
            is_active=True
        ).order_by("name")
        if self.instance is not None and getattr(self.instance, "employee_id", None):
            emp = self.instance.employee
            self.fields["employee_q"].initial = f"{emp.emp_code} - {emp.full_name}"
        apply_form_field_ui(self)
