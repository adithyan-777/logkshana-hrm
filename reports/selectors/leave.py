from datetime import date

from django.db.models import QuerySet

from leave.models import LeaveBalance, LeaveRequest


def leave_balance_list(
    *,
    year: int,
    department_id: int | None = None,
    employee_id: int | None = None,
) -> QuerySet[LeaveBalance]:
    queryset = LeaveBalance.objects.filter(year=year).select_related(
        "employee",
        "employee__department",
        "leave_type",
    )

    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    return queryset.order_by("employee__first_name", "leave_type__name")


def leave_utilization_list(
    *,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
) -> QuerySet[LeaveRequest]:
    queryset = LeaveRequest.objects.filter(
        status=LeaveRequest.Status.APPROVED,
        start_date__lte=date_to,
        end_date__gte=date_from,
    ).select_related("employee", "employee__department", "leave_type")

    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    return queryset.order_by("-start_date", "employee__first_name")


def pending_leave_list(
    *,
    department_id: int | None = None,
    employee_id: int | None = None,
) -> QuerySet[LeaveRequest]:
    queryset = LeaveRequest.objects.filter(
        status=LeaveRequest.Status.PENDING,
    ).select_related("employee", "employee__department", "leave_type")

    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    return queryset.order_by("-start_date", "employee__first_name")
