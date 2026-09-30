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


class BaseModel(TimeStampedModel):
    """
    The default base most models should inherit from: timestamps.
    """

    class Meta:
        abstract = True
