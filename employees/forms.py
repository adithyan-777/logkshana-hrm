from django import forms

from employees.models import Department, Employee, Position


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
