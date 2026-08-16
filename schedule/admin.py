from django.contrib import admin

from schedule.models import (
    OvertimeRule,
    ScheduleAssignment,
    Shift,
    ShiftDay,
    TemporarySchedule,
    Timetable,
    TimetableBreak,
)


class TimetableBreakInline(admin.TabularInline):
    model = TimetableBreak
    extra = 0


class OvertimeRuleInline(admin.StackedInline):
    model = OvertimeRule
    extra = 0
    max_num = 1


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "type",
        "work_type",
        "check_in",
        "check_out",
        "is_active",
    )
    list_filter = ("type", "work_type", "is_active")
    search_fields = ("name", "code")
    inlines = [TimetableBreakInline, OvertimeRuleInline]


class ShiftDayInline(admin.TabularInline):
    model = ShiftDay
    extra = 0
    autocomplete_fields = ("timetable",)


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "cycle_unit", "cycle_count", "is_active")
    list_filter = ("cycle_unit", "is_active", "auto_shift")
    search_fields = ("name", "code")
    inlines = [ShiftDayInline]


@admin.register(ScheduleAssignment)
class ScheduleAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "assignment_type",
        "shift",
        "employee",
        "department",
        "start_date",
        "end_date",
    )
    list_filter = ("assignment_type", "shift")
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
        "department__name",
        "shift__name",
    )
    autocomplete_fields = ("shift", "employee", "department")
    list_select_related = ("shift", "employee", "department")


@admin.register(TemporarySchedule)
class TemporaryScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "date",
        "timetable",
        "overrides_normal_schedule",
    )
    list_filter = ("overrides_normal_schedule", "timetable")
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
        "reason",
    )
    autocomplete_fields = ("employee", "timetable")
    list_select_related = ("employee", "timetable")
