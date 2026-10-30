from django import forms

from attendance.models import AttendanceActivity
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
        # apply_form_field_ui rewrites empty_label only for single selects; the
        # multi widget must not render a blank <option>.
        self.fields["employee"].empty_label = None
    employee = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        ),
        required=False,
    )


class EmployeeMultiFilterForm(DateRangeFilterForm):
    """Date range + department + multi-select employee (punch log, work sessions)."""

    employee = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        ),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # apply_form_field_ui rewrites empty_label only for single selects; the
        # multi widget must not render a blank <option>.
        self.fields["employee"].empty_label = None


class PunchLogFilterForm(EmployeeMultiFilterForm):
    """Multi employee + direction filter for the punch log report."""

    direction = forms.ChoiceField(
        required=False,
        choices=[("", "All directions")] + AttendanceActivity.Direction.choices,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ChoiceField has no empty_label; the shared filter partial reads it
        # for the select placeholder. Note: apply_form_field_ui won't add one.
        self.fields["direction"].empty_label = "All directions"


class WorkSessionFilterForm(EmployeeMultiFilterForm):
    """Multi employee + session state filter for the work sessions report."""

    status = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All sessions"),
            ("open", "Missing checkout"),
            ("closed", "Checked out"),
        ],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].empty_label = "All sessions"


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
            ("present", "Present"),
            ("late", "Late"),
            ("early_out", "Early Out"),
            ("incomplete", "Incomplete"),
        ],
    )
