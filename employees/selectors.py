from django.db.models import Q, QuerySet

from employees.models import Employee


def employee_list(*, search: str = "") -> QuerySet[Employee]:
    queryset = (
        Employee.objects.select_related("department", "position")
        .order_by("emp_code", "first_name")
    )

    if search:
        queryset = queryset.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(emp_code__icontains=search)
            | Q(email__icontains=search)
        )

    return queryset
