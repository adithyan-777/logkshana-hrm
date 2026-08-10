from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django_tenants.admin import TenantAdminMixin

from companies.models import Company


@admin.register(Company)
class CompanyAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("name", "paid_until")
