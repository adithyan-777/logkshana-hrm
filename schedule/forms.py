from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from schedule.models import Schedule, Timetable, TimetableBreak
from schedule.services import (
    TIMETABLE_TIMES_ORDER_ERROR,
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


TimetableBreakFormSet = inlineformset_factory(
    Timetable,
    TimetableBreak,
    form=TimetableBreakForm,
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

    def clean(self):
        cleaned_data = super().clean()
        repeat = cleaned_data.get("repeat")
        repeat_every = cleaned_data.get("repeat_every")
        if repeat and repeat_every in (None, ""):
            self.add_error("repeat_every", "Repeat interval is required.")
        elif repeat and repeat_every is not None and repeat_every < 1:
            self.add_error("repeat_every", "Repeat interval must be at least 1.")
        return cleaned_data
