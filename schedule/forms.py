from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from common.forms import apply_form_field_ui
from employees.models import Department, Employee
from schedule.models import Schedule, Timetable, TimetableBreak
from schedule.services import (
    ASSIGNMENT_MODE_ALL_EXCEPT,
    ASSIGNMENT_MODE_DEPARTMENT,
    ASSIGNMENT_MODE_INDIVIDUAL,
    ASSIGNMENT_MODES,
    BREAK_OUTSIDE_WORK_ERROR,
    TIMETABLE_TIMES_ORDER_ERROR,
    resolve_assignment_employees,
    validate_break_within_timetable,
    validate_timetable_times,
)

TIME_INPUT = forms.TimeInput(attrs={"type": "time"})


class TimetableForm(forms.ModelForm):
    class Meta:
        model = Timetable
        fields = [
            "name",
            "code",
            "type",
            "check_in",
            "check_out",
            "check_out_cross_days",
            "work_minutes",
            "check_in_start",
            "check_in_end",
            "grace_period_check_out",
            "grace_period_minutes",
            "count_break_time_as_work_time",
            "multiple_in_out",
            "is_active",
        ]
        widgets = {
            "check_in": TIME_INPUT,
            "check_out": TIME_INPUT,
            "check_in_start": TIME_INPUT,
            "check_in_end": TIME_INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional integers: browsers submit "" when left blank; the model
        # defaults (0) apply instead of failing required validation.
        self.fields["check_out_cross_days"].required = False
        self.fields["grace_period_minutes"].required = False
        apply_form_field_ui(self)

    def clean_check_out_cross_days(self):
        return self.cleaned_data.get("check_out_cross_days") or 0

    def clean_grace_period_minutes(self):
        return self.cleaned_data.get("grace_period_minutes") or 0

    def clean(self):
        cleaned_data = super().clean()
        try:
            validate_timetable_times(
                check_in=cleaned_data.get("check_in"),
                check_out=cleaned_data.get("check_out"),
                check_out_cross_days=cleaned_data.get("check_out_cross_days"),
            )
        except ValidationError:
            self.add_error("check_out_cross_days", TIMETABLE_TIMES_ORDER_ERROR)

        timetable_type = cleaned_data.get("type")
        work_minutes = cleaned_data.get("work_minutes")
        if (
            timetable_type == Timetable.Type.FLEXIBLE
            and work_minutes in (None, "")
        ):
            self.add_error(
                "work_minutes",
                "Required working minutes must be set for flexible timetables.",
            )
        return cleaned_data


class TimetableBreakForm(forms.ModelForm):
    class Meta:
        model = TimetableBreak
        fields = [
            "name",
            "break_time_type",
            "break_time_minutes",
            "start_time",
            "end_time",
            "grace_period_check_out",
            "grace_period_minutes",
        ]
        widgets = {
            "start_time": TIME_INPUT,
            "end_time": TIME_INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grace_period_minutes"].required = False
        apply_form_field_ui(self)

    def has_changed(self) -> bool:
        # A break row with no name/times means "no break". Model defaults
        # (e.g. break_time_type="fixed") would otherwise mark a blank extra
        # row as changed, forcing validation on rows the user never touched.
        meaningful = ("name", "start_time", "end_time", "break_time_minutes")
        data = self.data or {}
        if not any(data.get(self.add_prefix(name)) for name in meaningful):
            return False
        return super().has_changed()

    def clean_grace_period_minutes(self):
        return self.cleaned_data.get("grace_period_minutes") or 0

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        if start_time and end_time and end_time <= start_time:
            self.add_error("end_time", "End time must be after start time.")

        break_time_type = cleaned_data.get("break_time_type")
        break_time_minutes = cleaned_data.get("break_time_minutes")
        if (
            break_time_type == TimetableBreak.BreakType.FLEXIBLE
            and break_time_minutes in (None, "")
        ):
            self.add_error(
                "break_time_minutes",
                "Break minutes are required for flexible breaks.",
            )
        return cleaned_data


class BaseTimetableBreakFormSet(forms.BaseInlineFormSet):
    """Cross-row break validation: containment + no overlaps.

    Containment needs the parent timetable's work window. Views set
    ``formset.timetable_times = (check_in, check_out, cross_days)`` from
    the parent form; otherwise fall back to ``self.instance`` (edit path).
    """

    timetable_times = None

    def _work_window(self):
        if self.timetable_times is not None:
            return self.timetable_times
        instance = getattr(self, "instance", None)
        if instance is not None and getattr(instance, "pk", None):
            return (
                instance.check_in,
                instance.check_out,
                instance.check_out_cross_days or 0,
            )
        return (None, None, 0)

    def clean(self):
        super().clean()
        check_in, check_out, cross_days = self._work_window()
        windows = []
        for index, form in enumerate(self.forms):
            if not hasattr(form, "cleaned_data"):
                continue
            cleaned = form.cleaned_data
            if cleaned.get("DELETE"):
                continue
            start = cleaned.get("start_time")
            end = cleaned.get("end_time")
            if start is None or end is None:
                continue
            try:
                validate_break_within_timetable(
                    start_time=start,
                    end_time=end,
                    check_in=check_in,
                    check_out=check_out,
                    check_out_cross_days=cross_days or 0,
                )
            except ValidationError:
                form.add_error("start_time", BREAK_OUTSIDE_WORK_ERROR)
            windows.append((index, start, end))
        ordered = sorted(windows, key=lambda item: (item[1], item[2]))
        for (first_index, _, first_end), (second_index, second_start, _) in zip(
            ordered, ordered[1:]
        ):
            if second_start < first_end:
                self.forms[second_index].add_error(
                    "start_time",
                    "Breaks must not overlap each other.",
                )


TimetableBreakFormSet = inlineformset_factory(
    Timetable,
    TimetableBreak,
    form=TimetableBreakForm,
    formset=BaseTimetableBreakFormSet,
    fields=[
        "name",
        "break_time_type",
        "break_time_minutes",
        "start_time",
        "end_time",
        "grace_period_check_out",
        "grace_period_minutes",
    ],
    extra=1,
    can_delete=True,
)


def build_timetable_break_formset(*args, **kwargs) -> TimetableBreakFormSet:
    return TimetableBreakFormSet(*args, **kwargs)


class ScheduleAssignmentForm(forms.Form):
    """Add employees to a schedule: by department, person by person,
    or everyone except selected people."""

    schedule = forms.ModelChoiceField(
        queryset=Schedule.objects.filter(is_active=True).order_by("name"),
        label="Schedule",
    )
    mode = forms.ChoiceField(
        choices=ASSIGNMENT_MODES,
        initial=ASSIGNMENT_MODE_DEPARTMENT,
        widget=forms.RadioSelect,
        label="Who to add",
    )
    departments = forms.ModelMultipleChoiceField(
        queryset=Department.objects.order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Departments",
    )
    employees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        ),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="People",
    )
    excluded_employees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        ),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Exclude",
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Start date",
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
        label="End date (blank = open-ended)",
    )
    priority = forms.IntegerField(
        initial=0,
        required=False,
        label="Priority (higher wins overlaps)",
    )
    name = forms.CharField(
        max_length=100,
        required=False,
        label="Label (optional)",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["priority"].initial = self.fields["priority"].initial or 0
        apply_form_field_ui(self)
        self.resolved_employees = []

    def clean_priority(self):
        return self.cleaned_data.get("priority") or 0

    def clean(self):
        cleaned_data = super().clean()
        mode = cleaned_data.get("mode")
        departments = cleaned_data.get("departments") or []
        employees = cleaned_data.get("employees") or []
        excluded = cleaned_data.get("excluded_employees") or []

        if mode == ASSIGNMENT_MODE_DEPARTMENT and not departments:
            self.add_error(
                "departments", "Select at least one department."
            )
        elif mode == ASSIGNMENT_MODE_INDIVIDUAL and not employees:
            self.add_error("employees", "Select at least one person.")
        elif mode not in (
            ASSIGNMENT_MODE_DEPARTMENT,
            ASSIGNMENT_MODE_INDIVIDUAL,
            ASSIGNMENT_MODE_ALL_EXCEPT,
        ):
            self.add_error("mode", "Choose how to add people.")

        if self.errors:
            return cleaned_data

        resolved = resolve_assignment_employees(
            mode=mode,
            departments=departments,
            employees=employees,
            excluded=excluded,
        )
        if not resolved:
            self.add_error(
                "mode",
                "No active employees match this selection.",
            )
            return cleaned_data
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date must not be before start date.")
        self.resolved_employees = resolved
        return cleaned_data


class ScheduleForm(forms.ModelForm):
    class Meta:
        model = Schedule
        fields = [
            "name",
            "timetable",
            "repeat",
            "repeat_every",
            "repeat_unit",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["timetable"].queryset = Timetable.objects.filter(
            is_active=True
        ).order_by("name")
        apply_form_field_ui(self)

    def clean(self):
        cleaned_data = super().clean()
        repeat = cleaned_data.get("repeat")
        repeat_every = cleaned_data.get("repeat_every")
        if repeat and repeat_every in (None, ""):
            self.add_error("repeat_every", "Repeat interval is required.")
        elif repeat and repeat_every is not None and repeat_every < 1:
            self.add_error("repeat_every", "Repeat interval must be at least 1.")
        return cleaned_data
