from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Shared login account (lives in the public schema).

    Company membership is tracked on ``companies.Company.members``;
    app permissions come from the employees Role/Permission catalog.
    ``is_staff``/``is_superuser`` are global flags.
    """

    class Meta:
        ordering = ("-id",)
