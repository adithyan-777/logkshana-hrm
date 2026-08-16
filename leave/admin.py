from django.contrib import admin

from leave.models import (
    Holiday,
    LeaveApproval,
    LeaveBalance,
    LeaveBalanceTransaction,
    LeavePolicy,
    LeaveRequest,
    LeaveType,
)


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "paid",
        "requires_approval",
        "allow_half_day",
        "is_active",
    )
    list_filter = ("paid", "requires_approval", "is_active")
    search_fields = ("name", "code")


@admin.register(LeavePolicy)
class LeavePolicyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "leave_type",
        "entitlement_days",
        "accrual_type",
        "is_active",
    )
    list_filter = ("accrual_type", "is_active", "carry_forward")
    search_fields = ("name", "leave_type__name")
    autocomplete_fields = ("leave_type",)
    list_select_related = ("leave_type",)


class LeaveBalanceTransactionInline(admin.TabularInline):
    model = LeaveBalanceTransaction
    extra = 0


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "leave_type",
        "year",
        "entitled_days",
        "used_days",
        "pending_days",
    )
    list_filter = ("year", "leave_type")
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
        "leave_type__name",
    )
    autocomplete_fields = ("employee", "leave_type")
    list_select_related = ("employee", "leave_type")
    inlines = [LeaveBalanceTransactionInline]


class LeaveApprovalInline(admin.TabularInline):
    model = LeaveApproval
    extra = 0
    autocomplete_fields = ("approver",)


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "leave_type",
        "start_date",
        "end_date",
        "days",
        "status",
    )
    list_filter = ("status", "duration_type", "leave_type")
    search_fields = (
        "employee__emp_code",
        "employee__first_name",
        "employee__last_name",
        "leave_type__name",
    )
    autocomplete_fields = ("employee", "leave_type", "created_by")
    list_select_related = ("employee", "leave_type")
    inlines = [LeaveApprovalInline]


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ("name", "date", "end_date", "holiday_type", "is_active")
    list_filter = ("holiday_type", "is_active")
    search_fields = ("name",)
