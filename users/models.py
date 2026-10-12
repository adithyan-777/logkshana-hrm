from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class User(AbstractUser):
    """Shared login account (lives in the public schema).

    Company membership is tracked on ``companies.Company.members``;
    app permissions come from the employees Role/Permission catalog.
    ``is_staff``/``is_superuser`` are global flags.

    Email is unique case-insensitively (blank exempt): login by email
    must resolve to exactly one account.
    """

    class Meta:
        ordering = ("-id",)
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="uniq_user_email_ci",
                condition=~Q(email=""),
            ),
        ]
