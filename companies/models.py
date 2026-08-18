from django.db import models

from django_tenants.models import TenantMixin, DomainMixin

from common.models import BaseModel


class Company(TenantMixin):
    name = models.CharField(max_length=100)
    paid_until = models.DateField()
    on_trial = models.BooleanField()
    created_on = models.DateField(auto_now_add=True)

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True

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


class Domain(DomainMixin):
    pass
