from django.core.exceptions import ValidationError
from django.db import transaction

from leave.models import Holiday, LeavePolicy, LeaveRequest, LeaveType


@transaction.atomic
def leave_type_create(
    *,
    name: str,
    code: str,
    description: str = "",
    paid: bool = True,
    requires_approval: bool = True,
    allow_half_day: bool = True,
    allow_negative_balance: bool = False,
    is_active: bool = True,
) -> LeaveType:
    leave_type = LeaveType(
        name=name,
        code=code,
        description=description,
        paid=paid,
        requires_approval=requires_approval,
        allow_half_day=allow_half_day,
        allow_negative_balance=allow_negative_balance,
        is_active=is_active,
    )
    leave_type.full_clean()
    leave_type.save()
    return leave_type


@transaction.atomic
def leave_policy_create(
    *,
    leave_type: LeaveType,
    name: str,
    entitlement_days=0,
    accrual_type: str,
    accrual_days=0,
    carry_forward: bool = False,
    max_carry_forward_days=None,
    expiry_enabled: bool = False,
    expiry_days=None,
    minimum_service_days: int = 0,
    is_active: bool = True,
) -> LeavePolicy:
    policy = LeavePolicy(
        leave_type=leave_type,
        name=name,
        entitlement_days=entitlement_days,
        accrual_type=accrual_type,
        accrual_days=accrual_days,
        carry_forward=carry_forward,
        max_carry_forward_days=max_carry_forward_days,
        expiry_enabled=expiry_enabled,
        expiry_days=expiry_days,
        minimum_service_days=minimum_service_days,
        is_active=is_active,
    )
    policy.full_clean()
    policy.save()
    return policy


@transaction.atomic
def leave_request_create(
    *,
    employee,
    leave_type: LeaveType,
    start_date,
    end_date,
    duration_type: str,
    days,
    start_half: bool = False,
    end_half: bool = False,
    reason: str = "",
    status: str = LeaveRequest.Status.DRAFT,
    created_by=None,
) -> LeaveRequest:
    leave_request = LeaveRequest(
        employee=employee,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        duration_type=duration_type,
        days=days,
        start_half=start_half,
        end_half=end_half,
        reason=reason,
        status=status,
        created_by=created_by,
    )
    leave_request.full_clean()
    _validate_leave_request(leave_request)
    leave_request.save()
    return leave_request


@transaction.atomic
def holiday_create(
    *,
    name: str,
    date,
    end_date=None,
    holiday_type: str,
    description: str = "",
    is_active: bool = True,
) -> Holiday:
    holiday = Holiday(
        name=name,
        date=date,
        end_date=end_date,
        holiday_type=holiday_type,
        description=description,
        is_active=is_active,
    )
    holiday.full_clean()
    _validate_holiday(holiday)
    holiday.save()
    return holiday


def _validate_leave_request(leave_request: LeaveRequest) -> None:
    if leave_request.end_date < leave_request.start_date:
        raise ValidationError("End date must be on or after start date.")


def _validate_holiday(holiday: Holiday) -> None:
    if holiday.end_date and holiday.end_date < holiday.date:
        raise ValidationError("Holiday end date must be on or after start date.")
