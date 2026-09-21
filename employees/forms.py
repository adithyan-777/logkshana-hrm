from django import forms

from common.forms import apply_form_field_ui

from employees.models import Department, Employee, Permission, Position, Role
from employees.permission_catalog import permissions_grouped_choices


class EmployeeForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        min_length=8,
        widget=forms.PasswordInput(render_value=False),
        help_text=(
            "Min 8 characters; can't be too similar to the name/email, "
            "entirely numeric, or a commonly used password. "
            "On edit, leave blank to keep the current password."
        ),
    )

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
        self.fields["mobile"].required = False
        # Password is required when creating, optional when editing.
        if self.instance is None or not self.instance.pk:
            self.fields["password"].required = True
            self.fields["password"].help_text = (
                "Min 8 characters; can't be too similar to the name/email, "
                "entirely numeric, or a commonly used password."
            )
        else:
            self.fields["password"].required = False
        apply_form_field_ui(self)


    def _password_check_user(self):
        """User-like object so validators can check similarity."""
        instance = getattr(self, "instance", None)
        existing = getattr(instance, "user", None)
        if existing is not None:
            return existing
        from users.models import User

        return User(
            username="",
            email=(self.cleaned_data.get("email") or ""),
        )

    def clean_password(self):
        from django.contrib.auth.password_validation import validate_password

        password = self.cleaned_data.get("password") or ""
        is_create = self.instance is None or not self.instance.pk
        if is_create and not password:
            raise forms.ValidationError("Password is required.")
        if password:
            try:
                validate_password(password, user=self._password_check_user())
            except forms.ValidationError as exc:
                raise forms.ValidationError(exc.messages)
        return password


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "code", "parent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Department.objects.order_by("name")
        apply_form_field_ui(self)


class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ["title", "code", "parent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Position.objects.order_by("title")
        apply_form_field_ui(self)


class PermissionForm(forms.ModelForm):
    class Meta:
        model = Permission
        fields = ["codename", "name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_ui(self)



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
        apply_form_field_ui(self)

