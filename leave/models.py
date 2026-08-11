from django.db import models
from common.models import BaseModel
# Create your models here.

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class LeaveType(BaseModel):
    """
    Examples:
        Annual Leave
        Sick Leave
        Casual Leave
        Unpaid Leave
        Maternity Leave
    """

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)

    description = models.TextField(blank=True)

    paid = models.BooleanField(default=True)

    requires_approval = models.BooleanField(default=True)

    allow_half_day = models.BooleanField(default=True)

    allow_negative_balance = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LeavePolicy(BaseModel):
    """
    Defines how a leave type is granted/calculated.

    Keep this separate from LeaveType because the same leave type
    may eventually have different policies for different employee
    groups.
    """

    class AccrualType(models.TextChoices):
        YEARLY = "yearly", "Yearly"
        MONTHLY = "monthly", "Monthly"
        NONE = "none", "No Accrual"

    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.CASCADE,
        related_name="policies",
    )

    name = models.CharField(max_length=100)

    entitlement_days = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    accrual_type = models.CharField(
        max_length=20,
        choices=AccrualType.choices,
        default=AccrualType.YEARLY,
    )

    accrual_days = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    carry_forward = models.BooleanField(default=False)

    max_carry_forward_days = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    expiry_enabled = models.BooleanField(default=False)

    expiry_days = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    minimum_service_days = models.PositiveIntegerField(
        default=0,
        help_text="Employee must complete this many days before becoming eligible.",
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LeaveBalance(BaseModel):
    """
    Current leave balance for an employee.

    Example:

        Annual Leave
        Entitled: 30
        Carried: 5
        Used: 12
        Pending: 2
        Remaining: 21
    """

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="leave_balances",
    )

    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.PROTECT,
        related_name="balances",
    )

    year = models.PositiveIntegerField()

    entitled_days = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
    )

    carried_forward_days = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
    )

    adjustment_days = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
    )

    used_days = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
    )

    pending_days = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "leave_type", "year"],
                name="unique_employee_leave_balance",
            )
        ]

        indexes = [
            models.Index(
                fields=["employee", "year"],
            ),
        ]

    @property
    def total_entitlement(self):
        return self.entitled_days + self.carried_forward_days + self.adjustment_days

    @property
    def available_days(self):
        return self.total_entitlement - self.used_days - self.pending_days


class LeaveBalanceTransaction(BaseModel):
    """
    Audit trail for balance changes.

    Do not directly change balances without creating a transaction.
    """

    class TransactionType(models.TextChoices):
        ENTITLEMENT = "entitlement", "Entitlement"
        ACCRUAL = "accrual", "Accrual"
        CARRY_FORWARD = "carry_forward", "Carry Forward"
        ADJUSTMENT = "adjustment", "Adjustment"
        LEAVE_USED = "leave_used", "Leave Used"
        LEAVE_REVERSED = "leave_reversed", "Leave Reversed"
        EXPIRY = "expiry", "Expiry"

    balance = models.ForeignKey(
        LeaveBalance,
        on_delete=models.CASCADE,
        related_name="transactions",
    )

    transaction_type = models.CharField(
        max_length=30,
        choices=TransactionType.choices,
    )

    days = models.DecimalField(
        max_digits=7,
        decimal_places=2,
    )

    reference = models.CharField(
        max_length=255,
        blank=True,
    )

    notes = models.TextField(blank=True)


class LeaveRequest(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class DurationType(models.TextChoices):
        FULL_DAY = "full_day", "Full Day"
        HALF_DAY = "half_day", "Half Day"
        HOURLY = "hourly", "Hourly"

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="leave_requests",
    )

    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.PROTECT,
        related_name="requests",
    )

    start_date = models.DateField()
    end_date = models.DateField()

    duration_type = models.CharField(
        max_length=20,
        choices=DurationType.choices,
        default=DurationType.FULL_DAY,
    )

    days = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    start_half = models.BooleanField(default=False)
    end_half = models.BooleanField(default=False)

    reason = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leave_requests_created",
    )

    class Meta:
        ordering = ["-start_date"]

        indexes = [
            models.Index(
                fields=["employee", "start_date", "end_date"],
            ),
            models.Index(
                fields=["status"],
            ),
        ]

    def __str__(self):
        return f"{self.employee} - {self.leave_type}"


class LeaveApproval(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    leave_request = models.ForeignKey(
        LeaveRequest,
        on_delete=models.CASCADE,
        related_name="approvals",
    )

    level = models.PositiveIntegerField()

    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leave_approvals",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    comment = models.TextField(blank=True)

    acted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["level"]

        constraints = [
            models.UniqueConstraint(
                fields=["leave_request", "level"],
                name="unique_leave_approval_level",
            )
        ]


class Holiday(BaseModel):
    class HolidayType(models.TextChoices):
        PUBLIC = "public", "Public Holiday"
        COMPANY = "company", "Company Holiday"
        OPTIONAL = "optional", "Optional Holiday"

    name = models.CharField(max_length=150)

    date = models.DateField()

    end_date = models.DateField(
        null=True,
        blank=True,
    )

    holiday_type = models.CharField(
        max_length=20,
        choices=HolidayType.choices,
        default=HolidayType.PUBLIC,
    )

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["date"]

        indexes = [
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return self.name
