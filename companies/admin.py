from django.contrib import admin
from django_tenants.admin import TenantAdminMixin

from companies.models import Company, Domain
from companies.models import DeviceBrand, DeviceType, Device, Branch

@admin.register(Company)
class CompanyAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("name", "schema_name", "paid_until", "on_trial", "created_on")
    list_filter = ("on_trial",)
    search_fields = ("name", "schema_name")


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("domain",)
    autocomplete_fields = ("tenant",)

@admin.register(DeviceBrand)
class DeviceBrandAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)

@admin.register(DeviceType)
class DeviceTypeAdmin(admin.ModelAdmin):
    list_display = ("brand", "model_name", "description", "is_active")
    list_filter = ("is_active",)
    search_fields = ("brand__name", "model_name")

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("serial_number", "name", "company", "branch", "device_type", "is_active")
    list_filter = ("is_active",)
    search_fields = ("serial_number", "name")
    autocomplete_fields = ("company", "branch", "device_type")

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "code")
    list_filter = ("company",)
    search_fields = ("name", "code")
    autocomplete_fields = ("company",)