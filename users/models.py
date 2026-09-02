from django.db import models
from tenant_users.tenants.models import UserProfile


class TenantUser(UserProfile):
    username = models.CharField(max_length=150, unique=True, db_index=True)

    REQUIRED_FIELDS = ["username"]
