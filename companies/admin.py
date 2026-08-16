from django.contrib import admin
from django_tenants.admin import TenantAdminMixin

from companies.models import Company, Domain


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
