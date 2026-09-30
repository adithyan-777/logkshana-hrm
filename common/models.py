import uuid

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """
    Adds created/updated timestamps to any model that inherits from it.
    Use this as a base for almost everything.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """
    Replaces the default auto-incrementing integer PK with a UUID.
    Useful if you'll expose IDs in APIs/URLs and don't want sequential
    IDs leaking record counts or being guessable.
    Optional — skip this if you're fine with default integer PKs.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class AuditModel(TimeStampedModel):
    """
    Tracks who created/modified a record — useful for attendance
    corrections, schedule changes, etc. where you need accountability.
    """

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
        on_delete=models.SET_NULL,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
        on_delete=models.SET_NULL,
    )

    class Meta:
        abstract = True


class BaseModel(TimeStampedModel):
    """
    The default base most models should inherit from: timestamps.
    Use AuditModel instead (or in addition) for models where you need
    to know WHO made a change.
    """

    class Meta:
        abstract = True
