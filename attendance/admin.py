from django.contrib import admin
from django.core.exceptions import PermissionDenied

from attendance.models import (
    Attendance,
    AttendanceActivity,
    BreakSession,
    WorkSession,
)


@admin.register(AttendanceActivity)
class AttendanceActivityAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "punch_time",
        "direction",
        "method",
        "attendance",
        "external_id",
    )
    list_filter = ("direction", "method")
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
        "external_id",
    )
    autocomplete_fields = ("employee",)
    list_select_related = ("employee",)
    date_hierarchy = "punch_time"


class WorkSessionInline(admin.StackedInline):
    model = WorkSession
    fk_name = "attendance"
    extra = 0
    fields = ("day", "check_in", "check_out", "total_time")
    show_change_link = True


class BreakSessionInline(admin.TabularInline):
    model = BreakSession
    fk_name = "attendance"
    extra = 0
    fields = (
        "day",
        "work_session",
        "break_in",
        "break_out",
        "total_time",
    )
    show_change_link = True


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "day",
        "status",
        "total_work_time",
        "over_time",
        "is_calculated",
    )
    list_filter = ("status", "is_calculated")
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
    )
    autocomplete_fields = ("employee", "shift")
    list_select_related = ("employee", "shift")
    date_hierarchy = "day"
    inlines = [WorkSessionInline, BreakSessionInline]

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_calculated:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        if queryset.filter(is_calculated=True).exists():
            raise PermissionDenied(
                "Calculated attendance rows cannot be deleted in bulk."
            )
        super().delete_queryset(request, queryset)


@admin.register(WorkSession)
class WorkSessionAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "day",
        "is_open",
        "check_in",
        "check_out",
        "total_time",
    )
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
    )
    autocomplete_fields = ("employee", "in_punch", "out_punch")
    list_select_related = ("employee", "in_punch", "out_punch", "attendance")
    date_hierarchy = "day"

    @admin.display(boolean=True, description="Open")
    def is_open(self, obj) -> bool:
        return obj.check_out is None


@admin.register(BreakSession)
class BreakSessionAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "day",
        "is_open",
        "break_in",
        "break_out",
        "total_time",
        "work_session",
    )
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
    )
    autocomplete_fields = (
        "employee",
        "work_session",
        "in_punch",
        "out_punch",
    )
    list_select_related = (
        "employee",
        "work_session",
        "in_punch",
        "out_punch",
    )
    date_hierarchy = "day"

    @admin.display(boolean=True, description="Open")
    def is_open(self, obj) -> bool:
        return obj.break_out is None
