from django import forms

from common.forms import apply_form_field_ui

from employees.models import Department, Employee
from reports.utils import current_month_range


class DateRangeFilterForm(forms.Form):
    date_from = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_to = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.order_by("name"),
        required=False,
        empty_label="All departments",
    )
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        ),
        required=False,
        empty_label="All employees",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            date_from, date_to = current_month_range()
            self.fields["date_from"].initial = date_from
            self.fields["date_to"].initial = date_to
        apply_form_field_ui(self)


    def cleaned_date_range(self) -> tuple:
        date_from = self.cleaned_data.get("date_from")
        date_to = self.cleaned_data.get("date_to")
        if not date_from or not date_to:
            return current_month_range()
        return date_from, date_to


class IndividualReportFilterForm(DateRangeFilterForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_ui(self)
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        ),
        required=False,
        empty_label="Select employee",
    )


class ExceptionReportFilterForm(DateRangeFilterForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_ui(self)
    exception_type = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All exceptions"),
            ("late", "Late"),
            ("absent", "Absent"),
            ("incomplete", "Incomplete"),
            ("missing_punch", "Missing punch"),
        ],
    )


class LeaveReportFilterForm(forms.Form):
    report_type = forms.ChoiceField(
        required=False,
        choices=[
            ("balance", "Leave balance"),
            ("utilization", "Leave utilization"),
            ("pending", "Pending leave"),
        ],
        initial="balance",
    )
    date_from = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_to = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.order_by("name"),
        required=False,
        empty_label="All departments",
    )
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        ),
        required=False,
        empty_label="All employees",
    )
    year = forms.IntegerField(required=False, min_value=2000, max_value=2100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            date_from, date_to = current_month_range()
            self.fields["date_from"].initial = date_from
            self.fields["date_to"].initial = date_to
            self.fields["year"].initial = date_to.year
        apply_form_field_ui(self)


    def cleaned_date_range(self) -> tuple:
        date_from = self.cleaned_data.get("date_from")
        date_to = self.cleaned_data.get("date_to")
        if not date_from or not date_to:
            return current_month_range()
        return date_from, date_to

    def cleaned_year(self) -> int:
        year = self.cleaned_data.get("year")
        if year:
            return year
        return current_month_range()[1].year


class OvertimeReportFilterForm(DateRangeFilterForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_ui(self)
    status = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All statuses"),
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("auto_approved", "Auto approved"),
        ],
    )
