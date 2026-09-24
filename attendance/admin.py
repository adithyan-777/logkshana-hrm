from django.contrib import admin

from attendance.models import Attendance, AttendanceActivity


@admin.register(AttendanceActivity)
class AttendanceActivityAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "punch_time",
        "direction",
        "method",
        "is_attendance_processed",
        "external_id",
    )
    list_filter = ("direction", "method", "is_attendance_processed")
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
