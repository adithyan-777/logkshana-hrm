from django.conf import settings
from django.db import models

from django_tenants.models import DomainMixin, TenantMixin

from common.models import BaseModel


class Company(TenantMixin):
    name = models.CharField(max_length=100)
    paid_until = models.DateField()
    on_trial = models.BooleanField()
    created_on = models.DateField(auto_now_add=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_companies",
        null=True,
        blank=True,
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="companies",
        blank=True,
    )

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Owner implies membership.
        if self.owner_id and not self.members.filter(pk=self.owner_id).exists():
            self.members.add(self.owner_id)

    def add_user(self, user, **kwargs) -> None:
        """Attach an existing user to this company (membership)."""
        self.members.add(user)

    def remove_user(self, user) -> None:
        """Detach a user from this company (owner cannot be removed)."""
        if self.owner_id is not None and user.pk == self.owner_id:
            raise ValueError("Cannot remove the company owner.")
        self.members.remove(user)


class Branch(BaseModel):
    name = models.CharField(max_length=100)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    code = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.name} - {self.company.name}"


class Domain(DomainMixin):
    pass


class DeviceBrand(BaseModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.name


class DeviceType(BaseModel):
    brand = models.ForeignKey(
        DeviceBrand, on_delete=models.CASCADE, related_name="device_types"
    )
    model_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.brand_name} - {self.model_name}"


class Device(BaseModel):
    serial_number = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="devices"
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="devices")
    device_type = models.ForeignKey(
        DeviceType,
        on_delete=models.CASCADE,
        related_name="devices",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    last_gateway_log_id = models.PositiveIntegerField(default=0)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.serial_number} - {self.company.name} - {self.branch.name}"
