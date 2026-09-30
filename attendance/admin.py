from django.contrib import admin
from django.core.exceptions import PermissionDenied

from attendance.models import Attendance, AttendanceActivity


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
