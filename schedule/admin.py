from django.contrib import admin

from schedule.models import Schedule, Timetable, TimetableBreak


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
