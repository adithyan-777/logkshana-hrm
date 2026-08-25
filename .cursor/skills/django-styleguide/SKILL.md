---
name: django-styleguide
description: >-
  Applies HackSoft Django Styleguide conventions for models, services, selectors,
  APIs, serializers, settings, errors, testing, and Celery. Use when writing or
  reviewing Django/DRF code, structuring apps, placing business logic, or when
  the user mentions Django Styleguide, HackSoft, services, or selectors.
---

# HackSoft Django Styleguide

Source: [HackSoftware/Django-Styleguide](https://github.com/HackSoftware/Django-Styleguide)  
Example project: [Django-Styleguide-Example](https://github.com/HackSoftware/Django-Styleguide-Example)

Cherry-pick what fits the project; adapt when context differs.

## Core separation

**Business logic belongs in:**

- **Services** — write/mutate (create, update, side effects, external calls)
- **Selectors** — read/fetch (queries, filtering, visibility rules)
- Model `@property` / `clean` — simple, single-model, non-relational cases only

**Business logic does NOT belong in:**

- APIs, views, serializers, forms, form tags
- Model `save`, custom managers/querysets (as the main domain layer)
- Signals (except loose coupling / cache invalidation)

**Core vs interface:** behavior (services/selectors) is separate from how it is invoked (API, admin, management command, Celery task).

## Models

- Inherit a `BaseModel` with `created_at` / `updated_at` when the project uses one.
- **Validation in `clean`:** multi-field, non-relational, simple rules. Call `full_clean()` in services before `save()`.
- **Prefer DB constraints** (`CheckConstraint`, etc.) when possible. Since Django 4.1, `full_clean()` validates constraints too.
- **Complex or cross-model validation** → service layer.
- **`@property` / methods:** only for simple derived values on non-relational fields of the same instance. Multi-relation or N+1-prone logic → selector.
- **Test models** only when they have validation, properties, or methods. Prefer `full_clean()` without hitting DB when possible.

## Services

- Default: function in `<app>/services.py` (or `services/` package when large).
- **Naming:** `<entity>_<action>` (e.g. `user_create`, `course_update`). Keyword-only args unless zero/one arg.
- Type-annotate; use `@transaction.atomic` when needed.
- Pattern: build instance → `full_clean()` → `save()` → call other services/tasks.
- **Class-based services:** namespace for create/update flows, multi-step flows, or shared private helpers.
- **Updates:** use generic `model_update` for side-effect-free fields; handle side effects in the update service (see [reference.md](reference.md#cookbook)).

## Selectors

- Mirror service rules: `<entity>_<action>` in `<app>/selectors.py` or `selectors/` package.
- Return querysets, lists, or scalars as appropriate.
- **Filtering belongs in selectors** (often with `django-filter`). APIs serialize filter params; selectors apply them.
- Pagination: API layer (DRF paginator + helper) or selector — pick one pattern and stay consistent.

## APIs & serializers (DRF)

- **One API per operation** — CRUD = four APIs. Naming: `<Entity><Action>Api` (e.g. `CourseCreateApi`).
- Inherit plain `APIView` / `GenericAPIView`; avoid generic view classes that hide logic in serializers.
- **No business logic in APIs.** Allowed: auth, parse input, fetch object by id, call service/selector, serialize output.
- Nest **InputSerializer** and **OutputSerializer** inside the API class. Prefer plain `Serializer` over `ModelSerializer`.
- Reuse serializers sparingly. Use `inline_serializer` for nested shapes.
- **List API:** validate query params with `FilterSerializer` → pass to selector → paginate with shared helper.
- **Create:** validate input → `some_create(**serializer.validated_data)` → `201`.
- **Update:** validate input → `some_update(id=..., **data)` → `200`.
- **Object fetch:** consistent pattern (often `get_object` util at API level returning `None` on 404).
- **Heavy output serialization:** dedicated serialize function in `serializers.py` with prefetch/cache optimizations.

## URLs

- One URL per API/action. Group by domain in `*_patterns` lists; `include()` from root `urlpatterns`.

## Settings

- Split `config/django/` (Django settings) vs `config/settings/` (integrations).
- Everything imported in `base.py`; env-specific files only override.
- `config/env.py` with `django-environ`; optional `.env` via `env.read_env()`. Never commit `.env`.
- Optional integrations: `USE_*` flag defaulting to `False`; configure only when enabled.

## Errors (DRF)

- Decide error response shape early; document for frontend.
- Map `django.core.exceptions.ValidationError` → DRF `ValidationError` in custom exception handler.
- Two common shapes:
  1. DRF-style always `{"detail": ...}`
  2. HackSoft-style `{"message": "...", "extra": {}}` with validation fields under `extra.fields`
- See [reference.md](reference.md#errors--exception-handling) for handler implementations.

## Testing

```
app/tests/
├── factories.py
├── models/test_<model>.py
├── selectors/test_<selector>.py
└── services/test_<service>.py
```

- File: `test_<thing>.py`; class: `<Thing>Tests(TestCase)`.
- **Services:** exhaustive business logic tests; hit DB; mock external/async calls.
- **Models:** validation/properties without DB when possible.
- Use `factory_boy` / fakes for test data.

## Celery

- Tasks are thin: fetch ids → import and call service inside task body.
- Import task at module level with `_task` suffix; `transaction.on_commit(lambda: task.delay(...))`.
- Error handling / retries in task; failure callbacks call services.
- No business logic in tasks. Same split as APIs.

## Quick checklist (new feature)

1. Model + constraints/`clean` if simple
2. Selector(s) for reads/filters
3. Service(s) for writes/mutations
4. API class(es) with Input/Output serializers — delegate to services/selectors
5. URL patterns
6. Tests: service (primary), model/API as needed

## Additional resources

- Full guide with code examples: [reference.md](reference.md)
- Live example repo: https://github.com/HackSoftware/Django-Styleguide-Example
