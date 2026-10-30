---
name: django-forms
description: Django form patterns — ModelForm, field-level and cross-field validation, widget styling, and HTMX form submission. Use when building or changing forms, validating input, or handling form POST/GET flows in the Pattika/ITTISAL HRMS repo or any Django project.
---

# Django Forms

> In this repo (pattika), `AGENTS.md` is always loaded and wins on conflicts.

## In this repo

- Forms live in `<app>/forms.py` (e.g. `reports/forms.py`, `employees/forms.py`); report filter forms subclass a base form holding shared fields (`DateRangeFilterForm` pattern).
- **Styling is centralized**: `common/forms.apply_form_field_ui(form)` applies `form-input`/`form-select` classes and labels/placeholders — call it in `__init__` (again after `super().__init__` in subclasses that add fields of their own).
- Custom selects render through `templates/partials/select.html` (single + multi). A `ModelMultipleChoiceField` automatically renders the multi picker from the shared `reports/partials/filter_form.html#filter_form` partial; single selects come from `field.field.empty_label` (set it explicitly on `ChoiceField`s).
- Shared filter-form conventions: date range via `DateInput(attrs={"type": "date"})` + `cleaned_date_range()`; self-service views strip company-wide fields server-side (`_strip_company_filters`).
- Tests: per-file runs with tenant factories — `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m django test <app.tests.<module>> --keepdb`.

## Philosophy

- Prefer ModelForm for model-backed forms; keep validation in forms, not views.
- Always handle and display form errors; use `commit=False` when mutating the instance before saving.

## Validation

**Field-level** (`clean_<field>`): validate/transform one field, return the cleaned value or raise `ValidationError` — format checks, normalization, uniqueness.

**Cross-field** (`clean`): call `super().clean()` first, read `cleaned_data`, use `self.add_error(field, message)` for field-specific errors — password confirmation, conditional requirements.

## View Integration

- Check `request.method` explicitly; `request.POST` for POST, empty for GET.
- `form.save(commit=False)` to set FKs/ownership; redirect on success, re-render with the form on error.
- HTMX: use `is_htmx_partial(request)` (see **htmx-patterns**); return the form-part fragment with errors, or trigger events via `common.http.set_hx_trigger` (e.g. `showToast`, `closeModal` patterns in `employees/views.py`).

## Templates

- Show `form.non_field_errors` and per-field `field.errors`.
- Render `DateField`s as `.date-input` widgets so the report filters auto-apply on change.

## Widgets & Formsets

- Override in `Meta.widgets`; set attributes via `attrs` (`.date-input`, `.widget` patterns in the repo).
- Formsets: `inlineformset_factory` for related collections; validate `form.is_valid() and formset.is_valid()`; pass `instance` for edits.

## Pitfalls

- Validating in views instead of forms; redirecting without checking `is_valid()`.
- Forgetting `commit=False` before setting related fields.
- Adding fields in a subclass without re-running `apply_form_field_ui`/setting labels.
- Trusting client-side widget state instead of the hidden real input (select partial): forms/tests must assert on the real `<input>`/`<select multiple>` payload.
