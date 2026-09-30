from django import forms

from common.forms import apply_form_field_ui

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_ui(self)



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
        apply_form_field_ui(self)


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
        apply_form_field_ui(self)


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_ui(self)
