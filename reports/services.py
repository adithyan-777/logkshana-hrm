from django.contrib.auth import get_user_model
from django.db import transaction

from reports.columns import filter_columns, valid_column_keys
from reports.models import ReportColumnPreference

User = get_user_model()


def get_preferred_columns(user, report_key: str) -> list[str] | None:
    """Return the user's saved column keys for a report, or None if unsaved."""
    preference = ReportColumnPreference.objects.filter(
        user=user, report_key=report_key
    ).first()
    if preference is None:
        return None
    keys = [key for key in preference.columns if key in valid_column_keys(report_key)]
    return keys or None


@transaction.atomic
def save_preferred_columns(user, report_key: str, keys: list[str]) -> list[str]:
    """Persist the user's column selection; invalid keys are dropped."""
    columns = filter_columns(report_key, keys)
    saved_keys = [column.key for column in columns]
    ReportColumnPreference.objects.update_or_create(
        user=user,
        report_key=report_key,
        defaults={"columns": saved_keys},
    )
    return saved_keys
