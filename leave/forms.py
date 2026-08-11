from django import forms

from employees.models import Employee
from leave.models import Holiday, LeavePolicy, LeaveRequest, LeaveType

DATE_INPUT = forms.DateInput(attrs={"type": "date"})


class LeaveTypeForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = [
            "name",
            "code",
            "description",
            "paid",
            "requires_approval",
            "allow_half_day",
            "allow_negative_balance",
            "is_active",
        ]


class LeavePolicyForm(forms.ModelForm):
    class Meta:
        model = LeavePolicy
        fields = [
            "leave_type",
            "name",
            "entitlement_days",
            "accrual_type",
            "accrual_days",
            "carry_forward",
            "max_carry_forward_days",
            "expiry_enabled",
            "expiry_days",
            "minimum_service_days",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["leave_type"].queryset = LeaveType.objects.filter(
            is_active=True
        ).order_by("name")


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = [
            "employee",
            "leave_type",
            "start_date",
            "end_date",
            "duration_type",
            "days",
            "start_half",
            "end_half",
            "reason",
            "status",
        ]
        widgets = {
            "start_date": DATE_INPUT,
            "end_date": DATE_INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("first_name", "last_name")
        self.fields["leave_type"].queryset = LeaveType.objects.filter(
            is_active=True
        ).order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date must be on or after start date.")

        return cleaned_data


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = [
            "name",
            "date",
            "end_date",
            "holiday_type",
            "description",
            "is_active",
        ]
        widgets = {
            "date": DATE_INPUT,
            "end_date": DATE_INPUT,
        }

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get("date")
        end_date = cleaned_data.get("end_date")

        if date and end_date and end_date < date:
            self.add_error("end_date", "End date must be on or after start date.")

        return cleaned_data
