from django.db.models import Q, QuerySet

from leave.models import Holiday, LeavePolicy, LeaveRequest, LeaveType


def leave_type_list(*, search: str = "") -> QuerySet[LeaveType]:
    queryset = LeaveType.objects.order_by("name")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )

    return queryset


def leave_policy_list(*, search: str = "") -> QuerySet[LeavePolicy]:
    queryset = LeavePolicy.objects.select_related("leave_type").order_by("name")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(leave_type__name__icontains=search)
            | Q(leave_type__code__icontains=search)
        )

    return queryset


def leave_request_list(*, search: str = "") -> QuerySet[LeaveRequest]:
    queryset = LeaveRequest.objects.select_related("employee", "leave_type").order_by(
        "-start_date"
    )

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
            | Q(leave_type__name__icontains=search)
            | Q(status__icontains=search)
        )

    return queryset


def holiday_list(*, search: str = "") -> QuerySet[Holiday]:
    queryset = Holiday.objects.order_by("-date")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )

    return queryset
