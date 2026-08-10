from django.db import models
from django.conf import settings


class Department(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, null=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    def __str__(self):
        return self.name


class Position(models.Model):
    title = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, null=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    def __str__(self):
        return self.title


class Area(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, null=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    def __str__(self):
        return self.name


class AttendanceProvider(models.TextChoices):
    BIOTIME = "biotime", "BioTime"
    ZKTECO = "zkteco", "ZKTeco"
    HIKVISION = "hikvision", "Hikvision"
    MANUAL = "manual", "Manual / No Device"


class Employee(models.Model):
    """The canonical HRM employee record. Provider-specific sync state (BioTime,
    ZKTeco, etc.) lives on EmployeeDeviceLink, not here — Employee has no
    knowledge of any particular attendance device vendor.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_profile",
    )

    # Internal, HR-assigned employee code (payslips, org chart, etc.) —
    # distinct from any device_emp_code, which is provider-specific and lives
    # on EmployeeDeviceLink.
    emp_code = models.CharField(max_length=50, db_index=True, blank=True, null=True)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )

    email = models.EmailField(blank=True)
    mobile = models.CharField(max_length=30, blank=True)

    hire_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(
        default=True
    )  # employment status, not device sync status

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["emp_code"]

    def __str__(self):
        return f"{self.emp_code} - {self.first_name} {self.last_name}"


class EmployeeDeviceLink(models.Model):
    """Soft link between an Employee and their record on an external attendance
    provider (BioTime, ZKTeco, ...). `device_emp_code` is the code configured
    on that provider's device/panel — the same soft-link pattern biotime.
    BioTimeTransaction already uses, generalized across vendors.

    Usually one active link per employee, but the model allows more so a
    tenant can migrate providers or run two devices in parallel without a
    schema change.
    """

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="device_links"
    )
    provider = models.CharField(max_length=20, choices=AttendanceProvider.choices)

    device_emp_code = models.CharField(
        max_length=50, db_index=True
    )  # soft link, not FK
    external_id = models.CharField(
        max_length=100, blank=True
    )  # provider's own numeric/string id

    synced_at = models.DateTimeField(null=True, blank=True)
    sync_error = models.TextField(blank=True)  # last push/pull error, if any
    is_active = models.BooleanField(
        default=True
    )  # False when link is retired (device swap, etc.)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "device_emp_code"],
                condition=models.Q(is_active=True),
                name="unique_active_device_emp_code_per_provider",
            ),
        ]

    def __str__(self):
        return f"{self.employee_id} @ {self.provider}:{self.device_emp_code}"
