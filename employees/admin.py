from django.contrib import admin

from employees.models import Area, Department, Employee, Permission, Position, Role


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "parent")
    search_fields = ("name", "code")
    list_select_related = ("parent",)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("title", "code", "parent")
    search_fields = ("title", "code")
    list_select_related = ("parent",)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("codename", "name", "description")
    search_fields = ("codename", "name", "description")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "is_system")
    list_filter = ("is_system",)
    search_fields = ("name",)
    filter_horizontal = ("permissions",)


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "parent")
    search_fields = ("name", "code")
    list_select_related = ("parent",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "emp_code",
        "first_name",
        "last_name",
        "department",
        "position",
        "email",
        "is_active",
    )
    list_filter = ("is_active", "department", "position")
    search_fields = ("emp_code", "first_name", "last_name", "email", "mobile")
    autocomplete_fields = ("user", "department", "position")
    list_select_related = ("department", "position", "user")
