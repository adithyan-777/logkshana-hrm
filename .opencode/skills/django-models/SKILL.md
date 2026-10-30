---
name: django-models
description: Django model design patterns emphasizing query optimization, domain logic encapsulation, selectors/services layering. Use when designing models, writing migrations, optimizing queries (N+1, select_related), or implementing business logic in the Pattika/ITTISAL HRMS repo or any Django project.
---

# Django Model Patterns

> In this repo (pattika), `AGENTS.md` is always loaded and wins on conflicts.
> This skill adds general model/ORM best practices and repo-specific facts.

## In this repo

- Layering: views stay thin; query/data logic lives in **selectors** (`<app>/selectors/*.py`, keyword-only args returning querysets) and **services** (`<app>/services.py`, writes). Examples: `reports/selectors/`, `employees/selectors/`.
- Models inherit from a shared `BaseModel` (`common/models`); enums use `TextChoices` (e.g. `AttendanceActivity.Direction`, `Attendance.Status`).
- **Tenant context**: tenant data lives in tenant schemas — always scope data access inside `schema_context(tenant)` (`django_tenants.utils`); the public schema never holds tenant rows.
- Tests run per module (never the whole suite) with the **tenant factories** in `common/tests/factories.py` + `BaseTenantTestCase`:
  `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m django test <app.tests.<module>> --keepdb`
- Lint gate: `uv run ruff check .` (no pyright/mypy typing step).

## Core Philosophy: Fat Models, Thin Views

**Business logic belongs in models/managers/services, not views.** Views orchestrate workflows; models implement domain behavior.

- **Good**: Model methods handle state transitions (`post.publish()`, `order.cancel()`), permission checks (`post.is_editable_by(user)`), calculations (`invoice.calculate_total()`); use properties for read-only computed values; pass `update_fields` on partial saves.
- **Bad**: Views with if/else domain logic, computed values inline in views.

## Model Design

- `TextChoices`/`IntegerChoices` for status enums; `__str__()` and `Meta.ordering` on every model; indexes for frequently filtered/sorted fields; abstract bases for shared fields.
- Fields: `blank=True, default=""` for optional text (avoid `null`); `null=True` for optional FKs; `JSONField` for flexible metadata instead of many optional columns.

## QuerySet Patterns

- Prefer `QuerySet.as_manager()` with domain filters over custom managers; managers are for factory-style creates (`User.objects.create_user()`), QuerySets for filters/transformations.
- Chainable filters by state, date range, and user/tenant scope keep views, exports, and management commands consistent.

## Query Optimization: avoid N+1

1. `select_related()` for FK/OneToOne (see repo use: `.select_related("employee", "employee__department")`).
2. `prefetch_related()` for M2M/reverse relations; `Prefetch()` to filter and nest.
3. `only()`/`defer()` for heavy unused columns.
4. `.exists()` over truthiness; `.count()` over `len()`; `annotate()`/`aggregate()`/`F()` for database-side math.

## Signals: use sparingly

Prefer explicit service-layer calls; signals only for audit logging, cache invalidation, decoupled third-party reactions. If you control both trigger and reaction, don't use a signal.

## Migrations

- Generate with `makemigrations <app>`, review the file, then apply (`docker compose exec web python manage.py migrate`).
- Data migrations: `makemigrations --empty <app>`, access models via `apps.get_model(...)`, write forward + reverse, mind tenant schemas.

## Anti-Patterns

- Accessing relations in loops without `select_related`/`prefetch_related`.
- `if queryset:` / `len()` counts; loading full models for one field.
- Business logic in views; syncing signals for logic you own.
- Data changes outside `schema_context(tenant)`.

## Integration

- **django-forms**: ModelForm validation patterns.
- **htmx-patterns**: fragment views need the same query hygiene.
- **systematic-debugging**: root-cause workflow with per-file test runs.
