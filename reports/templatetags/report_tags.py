from django import template

register = template.Library()


@register.filter
def report_cell(row: dict, key: str):
    """Dict lookup by variable key; templates cannot do this natively."""
    return row.get(key, "")
