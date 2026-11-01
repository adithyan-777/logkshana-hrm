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
        # method is intentionally excluded: manual punches are always
        # MANUAL; BIOMETRIC can only come in via the gateway.
        fields = [
            "employee",
            "punch_time",
            "direction",
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
        # Manual forms never offer "Unknown": unclassified directions
        # can only come in via the gateway. Keep an existing unknown
        # value selectable so legacy/gateway punches still validate
        # when edited.
        direction_field = self.fields["direction"]
        unknown = AttendanceActivity.Direction.UNKNOWN
        # Only an existing record may carry unknown through (edit case).
        keep_unknown = (
            getattr(self.instance, "pk", None) is not None
            and self.instance.direction == unknown
        )
        direction_field.choices = [
            choice
            for choice in AttendanceActivity.Direction.choices
            if choice[0] != unknown or keep_unknown
        ]
        direction_field.widget.choices = direction_field.choices
        if self.instance is not None and getattr(self.instance, "employee_id", None):
            emp = self.instance.employee
            self.fields["employee_q"].initial = f"{emp.emp_code} - {emp.full_name}"
        apply_form_field_ui(self)


class AttendanceCorrectionForm(forms.ModelForm):
    """Direction-only correction form for a biometric punch.

    Employee and punch time are inherited from the corrected punch and
    shown read-only in the template; only the direction is editable.
    The corrected row's method is forced to CORRECTION by the service,
    so it is intentionally absent from the fields.
    """

    class Meta:
        model = AttendanceActivity
        fields = ("direction",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Same rule as AttendanceActivityForm: manual forms never offer
        # "Unknown"; keep an existing unknown value selectable so
        # legacy/gateway punches still validate.
        direction_field = self.fields["direction"]
        unknown = AttendanceActivity.Direction.UNKNOWN
        keep_unknown = (
            getattr(self.instance, "pk", None) is not None
            and self.instance.direction == unknown
        )
        direction_field.choices = [
            choice
            for choice in AttendanceActivity.Direction.choices
            if choice[0] != unknown or keep_unknown
        ]
        direction_field.widget.choices = direction_field.choices
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
