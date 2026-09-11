from django.conf import settings
from django.db import models


class ReportColumnPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="report_column_preferences",
    )
    report_key = models.CharField(max_length=64)
    columns = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "report_key"],
                name="unique_report_column_preference",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.report_key}"
