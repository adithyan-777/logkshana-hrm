from django import forms

from employees.models import Department, Employee, Permission, Position, Role
from employees.permission_catalog import permissions_grouped_choices


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "emp_code",
            "first_name",
            "last_name",
            "department",
            "position",
            "email",
            "mobile",
            "hire_date",
            "is_active",
        ]
        widgets = {
            "hire_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.order_by("name")
        self.fields["position"].queryset = Position.objects.order_by("title")
        self.fields["first_name"].required = True


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "code", "parent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Department.objects.order_by("name")


class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ["title", "code", "parent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Position.objects.order_by("title")


class PermissionForm(forms.ModelForm):
    class Meta:
        model = Permission
        fields = ["codename", "name", "description"]


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ["name", "permissions"]
        widgets = {
            "permissions": forms.CheckboxSelectMultiple(
                attrs={"class": "permission-multiselect"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["permissions"]
        field.queryset = Permission.objects.order_by("codename")
        field.required = False
        field.choices = permissions_grouped_choices(field.queryset)
