from django.contrib import admin

from attendance.models import (
    AttendanceCalculationRun,
    AttendanceCorrection,
    AttendancePeriod,
    AttendanceRule,
    AttendanceTransaction,
    DailyAttendance,
    OvertimeRecord,
)


@admin.register(AttendanceTransaction)
class AttendanceTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "timestamp",
        "direction",
        "source",
        "external_id",
    )
    list_filter = ("direction", "source")
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
        "external_id",
        "external_employee_id",
    )
    autocomplete_fields = ("employee",)
    list_select_related = ("employee",)
    date_hierarchy = "timestamp"


class AttendancePeriodInline(admin.TabularInline):
    model = AttendancePeriod
    extra = 0
    autocomplete_fields = ("check_in", "check_out")
    show_change_link = True


@admin.register(DailyAttendance)
class DailyAttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "date",
        "status",
        "first_in",
        "last_out",
        "worked_minutes",
        "is_calculated",
    )
    list_filter = ("status", "is_calculated")
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
    )
    autocomplete_fields = ("employee", "shift", "timetable")
    list_select_related = ("employee", "shift", "timetable")
    date_hierarchy = "date"
    inlines = [AttendancePeriodInline]


@admin.register(AttendanceCorrection)
class AttendanceCorrectionAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "date",
        "status",
        "check_in",
        "check_out",
        "requested_by",
    )
    list_filter = ("status",)
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
        "reason",
    )
    autocomplete_fields = ("employee", "requested_by", "approved_by")
    list_select_related = ("employee", "requested_by", "approved_by")


@admin.register(OvertimeRecord)
class OvertimeRecordAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "date",
        "minutes",
        "status",
        "requested_by",
    )
    list_filter = ("status",)
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
    )
    autocomplete_fields = (
        "employee",
        "daily_attendance",
        "requested_by",
        "approved_by",
    )
    list_select_related = ("employee", "daily_attendance")


@admin.register(AttendanceRule)
class AttendanceRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "require_check_in",
        "require_check_out",
        "late_grace_minutes",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(AttendanceCalculationRun)
class AttendanceCalculationRunAdmin(admin.ModelAdmin):
    list_display = (
        "start_date",
        "end_date",
        "status",
        "employees_count",
        "records_processed",
        "error_count",
        "started_at",
    )
    list_filter = ("status",)
    date_hierarchy = "start_date"
