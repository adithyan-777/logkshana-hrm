from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet

from employees.models import Employee


def employee_list(*, search: str = "") -> QuerySet[Employee]:
    queryset = Employee.objects.select_related("department", "position").order_by(
        "emp_code", "first_name"
    )

    if search:
        queryset = queryset.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(emp_code__icontains=search)
            | Q(email__icontains=search)
        )

    return queryset


def employee_get_by_emp_code(*, emp_code: str) -> Employee | None:
    matches = list(Employee.objects.filter(emp_code=emp_code, is_active=True)[:2])
    if len(matches) > 1:
        raise ValidationError(
            {"employee_id": "Multiple employees found for this employee id."}
        )
    if not matches:
        return None
    return matches[0]
