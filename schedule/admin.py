from django.contrib import admin

from schedule.models import (
    EmployeeScheduleAssignment,
    EmployeeScheduleOverride,
    Schedule,
    Timetable,
    TimetableBreak,
)


class TimetableBreakInline(admin.TabularInline):
    model = TimetableBreak
    extra = 0
    fields = (
        "name",
        "break_time_type",
        "break_time_minutes",
        "start_time",
        "end_time",
        "grace_period_check_out",
        "grace_period_minutes",
    )


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "type",
        "check_in",
        "check_out",
        "check_out_cross_days",
        "is_active",
    )
    list_filter = ("type", "is_active")
    search_fields = ("name", "code")
    inlines = [TimetableBreakInline]


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "timetable",
        "repeat",
        "repeat_every",
        "repeat_unit",
    )
    list_filter = ("repeat", "repeat_unit", "timetable")
    search_fields = ("name", "timetable__name")
    autocomplete_fields = ("timetable",)
    list_select_related = ("timetable",)


@admin.register(EmployeeScheduleAssignment)
class EmployeeScheduleAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "schedule",
        "start_date",
        "end_date",
        "priority",
        "is_active",
    )
    list_filter = ("is_active", "schedule")
    search_fields = ("name", "schedule__name", "employees__emp_code")
    autocomplete_fields = ("schedule",)
    list_select_related = ("schedule",)
    filter_horizontal = ("employees",)


@admin.register(EmployeeScheduleOverride)
class EmployeeScheduleOverrideAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "date",
        "schedule",
        "is_day_off",
    )
    list_filter = ("is_day_off",)
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
        "reason",
    )
    autocomplete_fields = ("employee", "schedule")
    list_select_related = ("employee", "schedule")
    date_hierarchy = "date"
