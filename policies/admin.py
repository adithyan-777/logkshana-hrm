from django.contrib import admin

from policies.models import AttendancePolicy, UnscheduledConfig


@admin.register(AttendancePolicy)
class AttendancePolicyAdmin(admin.ModelAdmin):
    list_display = ("id", "schedule_mode", "attendance_per_day", "updated_at")
    list_filter = ("schedule_mode", "attendance_per_day")
    search_fields = ("schedule_mode", "attendance_per_day")


@admin.register(UnscheduledConfig)
class UnscheduledConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "opening_time", "closing_time", "updated_at")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Surface what each time drives, at the place it's typed in.
        if db_field.name == "opening_time":
            kwargs["help_text"] = (
                "Day boundary for punch pairing: a next-day OUT closes the "
                "previous day's WorkSession only earlier than this — past it "
                "the punch is the new day's stray check-out (e.g. 04:00). "
                "Empty = no boundary (unbounded)."
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)
