from django.db import models

from common.models import BaseModel


class Company(BaseModel):
    name = models.CharField(max_length=100)
    paid_until = models.DateField()
    on_trial = models.BooleanField()
    created_on = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.name


class Branch(BaseModel):
    name = models.CharField(max_length=100)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    code = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.name} - {self.company.name}"


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
        return f"{self.brand.name} - {self.model_name}"


class Device(BaseModel):
    serial_number = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="devices"
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name="devices"
    )
    device_type = models.ForeignKey(
        DeviceType,
        on_delete=models.CASCADE,
        related_name="devices",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.serial_number} - {self.company.name} - {self.branch.name}"
