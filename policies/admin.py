from django.contrib import admin

from policies.models import AttendancePolicy


@admin.register(AttendancePolicy)
class AttendancePolicyAdmin(admin.ModelAdmin):
    list_display = ("id", "schedule_mode", "attendance_per_day", "updated_at")
    list_filter = ("schedule_mode", "attendance_per_day")
    search_fields = ("schedule_mode", "attendance_per_day")
