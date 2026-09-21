"""Shared form field UI helpers (labels, placeholders, control classes)."""

from django import forms

_SKIP_PLACEHOLDER_TYPES = frozenset(
    {"checkbox", "radio", "file", "hidden", "submit", "button", "image", "color"}
)


def _default_placeholder(field: forms.Field, name: str) -> str:
    """Build a sensible placeholder from the field label / input type."""
    label = (field.label or name.replace("_", " ")).strip()
    if not label:
        return ""

    widget = field.widget
    input_type = (
        widget.attrs.get("type") or getattr(widget, "input_type", "") or ""
    ).lower()

    if input_type == "email":
        return "e.g. name@company.com"
    if input_type == "tel":
        return "e.g. +974 5555 5555"
    if input_type == "password":
        return "Enter password"
    if input_type == "url":
        return "https://"
    if input_type in {"date", "month", "week"}:
        return "Select date"
    if input_type == "datetime-local":
        return "Select date and time"
    if input_type == "time":
        return "HH:MM"
    if input_type == "number" or isinstance(
        field, (forms.IntegerField, forms.DecimalField, forms.FloatField)
    ):
        return f"e.g. {label.lower()}"
    if isinstance(widget, forms.Textarea):
        return f"Enter {label.lower()}"
    return f"Enter {label.lower()}"


def apply_form_field_ui(
    form: forms.BaseForm,
    *,
    labels: dict[str, str] | None = None,
    placeholders: dict[str, str] | None = None,
    empty_labels: dict[str, str] | None = None,
) -> None:
    """Apply human labels, placeholders, and form-* CSS classes to fields.

    Placeholders default from each field's label when not overridden.
    Select fields get an empty_label of ``Select …`` when blank.
    """
    labels = labels or {}
    placeholders = placeholders or {}
    empty_labels = empty_labels or {}

    for name, field in form.fields.items():
        if name in labels:
            field.label = labels[name]

        widget = field.widget
        if isinstance(
            widget,
            (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect),
        ):
            continue

        input_type = (
            widget.attrs.get("type") or getattr(widget, "input_type", "") or ""
        ).lower()

        if isinstance(widget, (forms.Select, forms.SelectMultiple)):
            css = "form-select"
            if name in empty_labels and hasattr(field, "empty_label"):
                field.empty_label = empty_labels[name]
            elif (
                hasattr(field, "empty_label")
                and field.empty_label in (None, "", "---------")
            ):
                label = (field.label or name.replace("_", " ")).strip().lower()
                field.empty_label = f"Select {label}"
        elif isinstance(widget, forms.Textarea):
            css = "form-textarea"
        elif input_type == "color":
            # Color pickers use compact swatch classes (e.g. .tt-color), not .form-input.
            existing = widget.attrs.get("class", "")
            classes = [c for c in existing.split() if c and c != "form-input"]
            widget.attrs["class"] = " ".join(classes)
            css = None
        else:
            css = "form-input"

        if css:
            existing = widget.attrs.get("class", "")
            classes = existing.split()
            if css not in classes:
                widget.attrs["class"] = f"{existing} {css}".strip()

        if isinstance(widget, (forms.Select, forms.SelectMultiple)):
            continue

        if input_type in _SKIP_PLACEHOLDER_TYPES:
            continue

        placeholder = placeholders.get(name) or widget.attrs.get("placeholder")
        if not placeholder:
            placeholder = _default_placeholder(field, name)
        if placeholder:
            widget.attrs["placeholder"] = placeholder
