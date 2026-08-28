from django.contrib import admin

from companies.models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "paid_until", "on_trial", "created_on")
    list_filter = ("on_trial",)
    search_fields = ("name",)
