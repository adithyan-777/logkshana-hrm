import uuid
from django.db import models
from django.conf import settings


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


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()

    def all_with_deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    """
    Instead of hard-deleting rows (bad for attendance/audit history),
    mark them deleted and filter them out by default.
    Employees, schedules etc. should almost never be hard-deleted.
    """

    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()  # default manager — excludes deleted
    all_objects = models.Manager()  # explicit access to everything

    class Meta:
        abstract = True

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

    @property
    def is_deleted(self):
        return self.deleted_at is not None


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


class BaseModel(TimeStampedModel, SoftDeleteModel):
    """
    The default combo most models should inherit from:
    timestamps + soft delete. Use AuditModel instead (or in addition)
    for models where you need to know WHO made a change.
    """

    class Meta:
        abstract = True
