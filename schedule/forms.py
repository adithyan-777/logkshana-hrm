from datetime import datetime, time, timedelta
from re import sub

from django import forms

from common.forms import apply_form_field_ui
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

TIME_INPUT = forms.TimeInput(attrs={"type": "time", "class": "form-input"})
DATE_INPUT = forms.DateInput(attrs={"type": "date", "class": "form-input"})


def _slug_code(name: str) -> str:
    raw = sub(r"[^A-Za-z0-9]+", "-", (name or "").strip()).strip("-").upper()
    return (raw[:50] or "TT")


def _minutes_to_hm(total: int | None) -> tuple[int, int]:
    total = int(total or 0)
    return total // 60, total % 60


def _hm_to_minutes(hours, minutes) -> int | None:
    if hours in (None, "") and minutes in (None, ""):
        return None
    return int(hours or 0) * 60 + int(minutes or 0)


def _shift_time(value: time | None, delta_minutes: int) -> time | None:
    if value is None:
        return None
    base = datetime.combine(datetime(2000, 1, 1).date(), value)
    return (base + timedelta(minutes=delta_minutes)).time()


def _style_fields(form: forms.BaseForm) -> None:
    for field in form.fields.values():
        widget = field.widget
        if isinstance(
            widget,
            (forms.CheckboxInput, forms.RadioSelect, forms.HiddenInput, forms.FileInput),
        ):
            continue
        classes = widget.attrs.get("class", "")
        if isinstance(widget, forms.Select):
            if "form-select" not in classes:
                widget.attrs["class"] = f"{classes} form-select".strip()
        elif "form-input" not in classes:
            widget.attrs["class"] = f"{classes} form-input".strip()


class TimetableForm(forms.ModelForm):
    """Hik-Connect–inspired timetable form mapped onto Timetable + TimetableBreak."""

    cross_day = forms.BooleanField(
        required=False,
        label="Cross-day shift",
        help_text="Turn on when check-out falls on the next calendar day.",
    )
    work_hours = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=24,
        label="Hours",
        widget=forms.NumberInput(
            attrs={"class": "form-input", "placeholder": "8", "min": "0", "max": "24"}
        ),
    )
    work_mins = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=59,
        label="Minutes",
        widget=forms.NumberInput(
            attrs={"class": "form-input", "placeholder": "0", "min": "0", "max": "59"}
        ),
    )
    enable_break = forms.BooleanField(required=False, label="Enable break time")
    break_start = forms.TimeField(
        required=False,
        label="Break start",
        widget=forms.TimeInput(attrs={"type": "time", "class": "form-input"}),
    )
    break_end = forms.TimeField(
        required=False,
        label="Break end",
        widget=forms.TimeInput(attrs={"type": "time", "class": "form-input"}),
    )
    break_duration = forms.IntegerField(
        required=False,
        min_value=0,
        label="Break duration (minutes)",
        widget=forms.NumberInput(
            attrs={"class": "form-input", "placeholder": "e.g. 60"}
        ),
    )
    count_break_as_work = forms.BooleanField(
        required=False,
        label="Count break time as work hours",
    )
    latest_check_in_enabled = forms.BooleanField(
        required=False,
        label="Latest check-in time",
        help_text=(
            "If the actual check-in is later than this time, "
            "the attendance status is marked as Late."
        ),
    )
    latest_check_in = forms.TimeField(
        required=False,
        label="Latest check-in",
        widget=forms.TimeInput(attrs={"type": "time", "class": "form-input"}),
    )

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
        labels = {
            "name": "Name",
            "code": "Code",
            "type": "Shift type",
            "work_type": "Work type",
            "workday": "Workday value",
            "check_in": "Work period start",
            "check_out": "Work period end",
            "work_minutes": "Required work minutes",
            "check_in_start": "Check-in window start",
            "check_in_end": "Check-in window end",
            "check_out_start": "Check-out window start",
            "check_out_end": "Check-out window end",
            "check_in_cross_days": "Check-in day offset",
            "check_out_cross_days": "Check-out day offset",
            "require_check_in": "Require check-in",
            "require_check_out": "Require check-out",
            "allow_late_in": "Allow late check-in",
            "allow_early_out": "Allow early check-out",
            "late_in_grace_minutes": "Late grace (minutes)",
            "early_out_grace_minutes": "Early-out grace (minutes)",
            "multiple_in_out": "Allow multiple in/out",
            "day_change_time": "Day-change time",
            "color": "Color",
            "is_active": "Active",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-input", "placeholder": "e.g. Morning shift"}
            ),
            "code": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Auto from name if blank",
                }
            ),
            "type": forms.RadioSelect(),
            "work_type": forms.Select(attrs={"class": "form-select"}),
            "workday": forms.NumberInput(
                attrs={"class": "form-input", "placeholder": "1", "step": "0.25"}
            ),
            "check_in": TIME_INPUT,
            "check_out": TIME_INPUT,
            "work_minutes": forms.HiddenInput(),
            "check_in_start": TIME_INPUT,
            "check_in_end": TIME_INPUT,
            "check_out_start": TIME_INPUT,
            "check_out_end": TIME_INPUT,
            "check_in_cross_days": forms.NumberInput(
                attrs={"class": "form-input", "min": "0", "max": "3"}
            ),
            "check_out_cross_days": forms.NumberInput(
                attrs={"class": "form-input", "min": "0", "max": "3"}
            ),
            "late_in_grace_minutes": forms.NumberInput(
                attrs={"class": "form-input", "placeholder": "10"}
            ),
            "early_out_grace_minutes": forms.NumberInput(
                attrs={"class": "form-input", "placeholder": "10"}
            ),
            "day_change_time": TIME_INPUT,
            "color": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].required = False
        self.fields["color"].required = False
        # Set widget first, then choices — Django keeps them in sync on the widget.
        self.fields["type"].widget = forms.RadioSelect()
        self.fields["type"].choices = [
            (Timetable.Type.NORMAL, "Normal Shift"),
            (Timetable.Type.FLEXIBLE, "Flexible Shift"),
        ]
        self.fields["color"].widget = forms.HiddenInput()
        if not self.initial.get("color") and not (
            self.instance and self.instance.pk and self.instance.color
        ):
            self.fields["color"].initial = "#14b8a6"
        if self.instance and self.instance.pk:
            self.fields["cross_day"].initial = self.instance.check_out_cross_days > 0
            hours, mins = _minutes_to_hm(self.instance.work_minutes)
            self.fields["work_hours"].initial = hours or 8
            self.fields["work_mins"].initial = mins
            primary = self.instance.breaks.order_by("start_time").first()
            if primary:
                self.fields["enable_break"].initial = True
                self.fields["break_start"].initial = primary.start_time
                self.fields["break_end"].initial = primary.end_time
                span = datetime.combine(
                    datetime(2000, 1, 1).date(), primary.end_time
                ) - datetime.combine(datetime(2000, 1, 1).date(), primary.start_time)
                self.fields["break_duration"].initial = max(
                    int(span.total_seconds() // 60), 0
                )
                self.fields["count_break_as_work"].initial = primary.paid
            if self.instance.check_in_end:
                self.fields["latest_check_in_enabled"].initial = True
                self.fields["latest_check_in"].initial = self.instance.check_in_end
        else:
            self.fields["work_hours"].initial = 8
            self.fields["work_mins"].initial = 0
            self.fields["check_in"].initial = time(9, 0)
            self.fields["check_out"].initial = time(18, 0)
        _style_fields(self)
        apply_form_field_ui(self)


    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("name") or ""
        code = (cleaned.get("code") or "").strip()
        if not code:
            cleaned["code"] = _slug_code(name)

        cleaned["check_in_cross_days"] = cleaned.get("check_in_cross_days") or 0
        cleaned["check_out_cross_days"] = cleaned.get("check_out_cross_days") or 0
        # Cross-day toggle forces at least next-day check-out; leaving it
        # off keeps the explicit check_out_cross_days value (advanced / tests).
        if cleaned.get("cross_day"):
            cleaned["check_out_cross_days"] = max(
                int(cleaned["check_out_cross_days"]), 1
            )

        shift_type = cleaned.get("type") or Timetable.Type.NORMAL
        if shift_type == Timetable.Type.FLEXIBLE:
            cleaned["work_minutes"] = _hm_to_minutes(
                cleaned.get("work_hours"), cleaned.get("work_mins")
            )
            if not cleaned["work_minutes"]:
                self.add_error(
                    "work_hours", "Enter required work hours for a flexible shift."
                )
        else:
            cleaned["work_minutes"] = cleaned.get("work_minutes") or None

        check_in = cleaned.get("check_in")
        check_out = cleaned.get("check_out")
        if check_in and not cleaned.get("check_in_start"):
            cleaned["check_in_start"] = _shift_time(check_in, -10)
        if check_in and not cleaned.get("check_in_end"):
            cleaned["check_in_end"] = _shift_time(check_in, 10)
        if check_out and not cleaned.get("check_out_start"):
            cleaned["check_out_start"] = _shift_time(check_out, -10)
        if check_out and not cleaned.get("check_out_end"):
            cleaned["check_out_end"] = _shift_time(check_out, 10)

        if cleaned.get("latest_check_in_enabled") and cleaned.get("latest_check_in"):
            cleaned["check_in_end"] = cleaned["latest_check_in"]
            cleaned["allow_late_in"] = True
        elif cleaned.get("latest_check_in_enabled") and not cleaned.get(
            "latest_check_in"
        ):
            self.add_error("latest_check_in", "Set the latest check-in time.")

        if cleaned.get("enable_break"):
            if not cleaned.get("break_start") or not cleaned.get("break_end"):
                self.add_error("break_start", "Set break start and end times.")
            elif cleaned["break_end"] <= cleaned["break_start"]:
                self.add_error("break_end", "Break end must be after break start.")

        if not cleaned.get("color"):
            cleaned["color"] = "#14b8a6"

        try:
            validate_timetable_times(
                check_in=cleaned.get("check_in"),
                check_out=cleaned.get("check_out"),
                check_in_cross_days=cleaned.get("check_in_cross_days"),
                check_out_cross_days=cleaned.get("check_out_cross_days"),
            )
        except ValidationError as exc:
            message_dict = getattr(exc, "message_dict", None)
            if message_dict:
                for field, messages in message_dict.items():
                    for message in messages:
                        self.add_error(field, message)
            else:
                self.add_error("check_out_cross_days", TIMETABLE_TIMES_ORDER_ERROR)
        return cleaned

    def service_kwargs(self) -> dict:
        """Model kwargs + optional primary break payload for services."""
        data = self.cleaned_data
        payload = {key: data.get(key) for key in self.Meta.fields}
        if data.get("enable_break") and data.get("break_start") and data.get("break_end"):
            payload["break_data"] = {
                "name": "Break",
                "start_time": data["break_start"],
                "end_time": data["break_end"],
                "paid": bool(data.get("count_break_as_work")),
                "minimum_minutes": int(data.get("break_duration") or 0),
            }
        else:
            payload["break_data"] = None
        return payload


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
        labels = {
            "name": "Shift name",
            "code": "Code",
            "auto_shift": "Auto shift",
            "cycle_unit": "Cycle unit",
            "cycle_count": "Cycle length",
            "is_active": "Active",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-input", "placeholder": "e.g. Weekday rotation"}
            ),
            "code": forms.TextInput(
                attrs={"class": "form-input", "placeholder": "e.g. WD"}
            ),
            "cycle_unit": forms.Select(attrs={"class": "form-select"}),
            "cycle_count": forms.NumberInput(
                attrs={"class": "form-input", "placeholder": "e.g. 7"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)
        apply_form_field_ui(self)


ShiftDayFormSet = inlineformset_factory(
    Shift,
    ShiftDay,
    fields=["day_number", "timetable"],
    extra=7,
    can_delete=True,
    labels={
        "day_number": "Day",
        "timetable": "Timetable",
    },
)


def build_shift_day_formset(*args, **kwargs) -> ShiftDayFormSet:
    formset = ShiftDayFormSet(*args, **kwargs)
    timetable_queryset = Timetable.objects.filter(is_active=True).order_by("name")
    for form in formset.forms:
        form.fields["timetable"].queryset = timetable_queryset
        form.fields["timetable"].empty_label = "Select timetable"
        form.fields["day_number"].widget.attrs.setdefault("placeholder", "1-7")
        _style_fields(form)
        apply_form_field_ui(form)
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
        labels = {
            "assignment_type": "Assignment type",
            "shift": "Shift",
            "start_date": "Start date",
            "end_date": "End date",
            "employee": "Employee",
            "department": "Department",
            "overwrite_existing": "Overwrite existing",
        }
        widgets = {
            "assignment_type": forms.Select(attrs={"class": "form-select"}),
            "shift": forms.Select(attrs={"class": "form-select"}),
            "employee": forms.Select(attrs={"class": "form-select"}),
            "department": forms.Select(attrs={"class": "form-select"}),
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
        self.fields["shift"].empty_label = "Select shift"
        self.fields["employee"].empty_label = "Select employee"
        self.fields["department"].empty_label = "Select department"
        _style_fields(self)
        apply_form_field_ui(self)


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
        labels = {
            "employee": "Employee",
            "date": "Date",
            "timetable": "Timetable",
            "reason": "Reason",
            "overrides_normal_schedule": "Overrides normal schedule",
        }
        widgets = {
            "employee": forms.Select(attrs={"class": "form-select"}),
            "timetable": forms.Select(attrs={"class": "form-select"}),
            "date": DATE_INPUT,
            "reason": forms.Textarea(
                attrs={
                    "class": "form-textarea",
                    "rows": 3,
                    "placeholder": "e.g. Cover for colleague",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("first_name", "last_name")
        self.fields["timetable"].queryset = Timetable.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["employee"].empty_label = "Select employee"
        self.fields["timetable"].empty_label = "Select timetable"
        _style_fields(self)
        apply_form_field_ui(self)

