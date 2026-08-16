from django.db import models
from django.conf import settings
from common.models import BaseModel
from companies.models import Branch


class Department(BaseModel):
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


class Position(BaseModel):
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


class Area(BaseModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    def __str__(self):
        return self.name

class EmployeeType(models.TextChoices):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERN = "intern"
    TEMPORARY = "temporary"
    VOLUNTEER = "volunteer"


class Employee(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_profile",
    )
    emp_code = models.CharField(max_length=50, db_index=True, blank=True, null=True)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)

    employee_type = models.CharField(max_length=50, choices=EmployeeType.choices, default=EmployeeType.FULL_TIME)

    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")

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
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.emp_code} - {self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
