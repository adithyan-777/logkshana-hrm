from django.contrib import admin

# Register your models here.

from users.models import TenantUser

@admin.register(TenantUser)
class TenantUserAdmin(admin.ModelAdmin):
    search_fields = ("username", "email")
    ordering = ("-id",)