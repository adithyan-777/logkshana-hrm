from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from employees.models import Department, Employee
from schedule.models import (
    ScheduleAssignment,
    Shift,
    ShiftDay,
    TemporarySchedule,
    Timetable,
)
from schedule.services import (
    TIMETABLE_TIMES_ORDER_ERROR,
    validate_timetable_times,
)

TIME_INPUT = forms.TimeInput(attrs={"type": "time"})
DATE_INPUT = forms.DateInput(attrs={"type": "date"})


class TimetableForm(forms.ModelForm):
    class Meta:
        model = Timetable
        fields = [
            "name",
            "code",
            "type",
            "work_type",
            "workday",
            "check_in",
            "check_out",
            "work_minutes",
            "check_in_start",
            "check_in_end",
            "check_out_start",
            "check_out_end",
            "check_in_cross_days",
            "check_out_cross_days",
            "require_check_in",
            "require_check_out",
            "allow_late_in",
            "allow_early_out",
            "late_in_grace_minutes",
            "early_out_grace_minutes",
            "multiple_in_out",
            "day_change_time",
            "color",
            "is_active",
        ]
        widgets = {
            "check_in": TIME_INPUT,
            "check_out": TIME_INPUT,
            "check_in_start": TIME_INPUT,
            "check_in_end": TIME_INPUT,
            "check_out_start": TIME_INPUT,
            "check_out_end": TIME_INPUT,
            "day_change_time": TIME_INPUT,
        }

    def clean(self):
        cleaned_data = super().clean()
        try:
            validate_timetable_times(
                check_in=cleaned_data.get("check_in"),
                check_out=cleaned_data.get("check_out"),
                check_in_cross_days=cleaned_data.get("check_in_cross_days"),
                check_out_cross_days=cleaned_data.get("check_out_cross_days"),
            )
        except ValidationError:
            self.add_error("check_out_cross_days", TIMETABLE_TIMES_ORDER_ERROR)
        return cleaned_data


class ShiftForm(forms.ModelForm):
    class Meta:
        model = Shift
        fields = [
            "name",
            "code",
            "auto_shift",
            "cycle_unit",
            "cycle_count",
            "is_active",
        ]


ShiftDayFormSet = inlineformset_factory(
    Shift,
    ShiftDay,
    fields=["day_number", "timetable"],
    extra=7,
    can_delete=True,
)


def build_shift_day_formset(*args, **kwargs) -> ShiftDayFormSet:
    formset = ShiftDayFormSet(*args, **kwargs)
    timetable_queryset = Timetable.objects.filter(is_active=True).order_by("name")
    for form in formset.forms:
        form.fields["timetable"].queryset = timetable_queryset
    return formset


class ScheduleAssignmentForm(forms.ModelForm):
    class Meta:
        model = ScheduleAssignment
        fields = [
            "assignment_type",
            "shift",
            "start_date",
            "end_date",
            "employee",
            "department",
            "overwrite_existing",
        ]
        widgets = {
            "start_date": DATE_INPUT,
            "end_date": DATE_INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["shift"].queryset = Shift.objects.filter(is_active=True).order_by(
            "name"
        )
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("first_name", "last_name")
        self.fields["department"].queryset = Department.objects.order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        assignment_type = cleaned_data.get("assignment_type")
        employee = cleaned_data.get("employee")
        department = cleaned_data.get("department")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date must be on or after start date.")

        if (
            assignment_type == ScheduleAssignment.AssignmentType.EMPLOYEE
            and not employee
        ):
            self.add_error("employee", "Required for employee assignments.")
        elif (
            assignment_type == ScheduleAssignment.AssignmentType.DEPARTMENT
            and not department
        ):
            self.add_error("department", "Required for department assignments.")

        return cleaned_data


class TemporaryScheduleForm(forms.ModelForm):
    class Meta:
        model = TemporarySchedule
        fields = [
            "employee",
            "date",
            "timetable",
            "reason",
            "overrides_normal_schedule",
        ]
        widgets = {
            "date": DATE_INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("first_name", "last_name")
        self.fields["timetable"].queryset = Timetable.objects.filter(
            is_active=True
        ).order_by("name")
