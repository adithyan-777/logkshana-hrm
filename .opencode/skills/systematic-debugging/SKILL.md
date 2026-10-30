---
name: systematic-debugging
description: Four-phase debugging methodology with root cause analysis for Django. Use when investigating bugs, test failures, or unexpected behavior — emphasizes NO FIXES WITHOUT ROOT CAUSE FIRST. Applies to the Pattika/ITTISAL HRMS repo and any Django project.
---

# Systematic Debugging for Django

## Core Principle

**NO FIXES WITHOUT ROOT CAUSE FIRST.** Never apply patches that mask underlying problems. Understand WHY something fails before fixing it.

> In this repo (pattika): run tests **per module** —
> `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m django test <app.tests.<module>> --keepdb`
> (`--keepdb` required; never the full suite). Tests use Django `unittest` +
> tenant factories (`common/tests/factories.py`) and `BaseTenantTestCase`;
> there is no pytest/pyright. Lint gate is `uv run ruff check .`.
> For live behavior in Docker: rebuild (`docker compose build web && docker compose up -d web`) before checking,
> then verify at `http://freshline.localhost:8000/…` (tenant header matters).

## Four-Phase Framework

### Phase 1: Reproduce and Investigate

Before touching any code:

1. **Write a failing test** that captures the bug behavior.
2. **Read error messages thoroughly** — every word matters.
3. **Examine recent changes** — `git diff`, `git log`.
4. **Trace data flow** to where bad values originate.

```python
# unittest-style reproduction test (repo conventions)
class BugReproductionTests(BaseTenantTestCase):
    def test_bug_reproduction(self):
        employee = employee_factory(first_name="Bug", emp_code="BUG-01")
        # act on the flow under test...
        response = self.client.get(reverse("daily_attendance_list"))
        self.assertEqual(response.status_code, 200)  # currently failing
```

Tenant/tenancy gotcha: data must exist **inside the tenant schema** — seed via `schema_context(tenant)`, not the public schema.

### Phase 2: Isolate

Narrow the problem:

```python
import logging
logger = logging.getLogger(__name__)

def problematic_view(request):
    logger.debug(f"HTMX: {request.headers.get('HX-Request')}")
    logger.debug(f"POST: {request.POST}")
    logger.debug(f"Valid: {form.is_valid()} Errors: {form.errors}")
```

Or drop into the debugger: `breakpoint()` inside the view/test (commands: n, s, c, p, q).

### Phase 3: Identify Root Cause

- Read the full stack trace; check violated assumptions.
- Classify: Is it data (wrong tenant schema / seed), logic (selector filter, service write), or presentation (template swap, fragment geometry, HTMX flags)?
- For HTMX/SPA UI bugs ("refresh lands me on a weird page", duplicated sections): suspect push/history and fragment-target problems first — that is a push/restore-class bug, not a view bug.

### Phase 4: Fix and Verify

1. Fix at the root cause.
2. The reproduction test passes.
3. Rerun the affected test module(s) individually (`--keepdb`), repeating per touched app.
4. Verify live in Docker when UI/templates changed; `ruff check .` clean.

## Query Debugging

```python
from django.test.utils import CaptureQueriesContext
from django.db import connection

with CaptureQueriesContext(connection) as ctx:
    list(SomeModel.objects.select_related("relation"))
print(len(ctx))  # assert in tests to guard against N+1
```

SQL logging (temporarily) in settings:

```python
LOGGING = {"loggers": {"django.db.backends": {"level": "DEBUG", "handlers": ["console"]}}}
```

## Common Django Issues

- **N+1 queries**: relation access in loops — add `select_related()`/`prefetch_related()` (repos: see `reports/selectors/*`).
- **Form not saving**: `is_valid()` → did you call `.save()`? `commit=False` → did you `.save()` the instance?
- **CSRF 403**: `{% csrf_token %}` in the form (HTMX gets it from body-level `hx-headers` in `templates/base.html`).
- **Migrations**: `manage.py showmigrations`; avoid `--fake` unless you know both sides' schema states. Tenant schemas: run migrations per tenant/tenant-group as the repo's stack does.
- **Silent template rendering issues**: a multi-line `{% … %}` token renders as raw text with no error — scan for tokens spanning lines (AGENTS §1.1).

## Debugging HTMX

```html
<script>htmx.logAll();</script>
```

Check request class headers: `HX-Request`, `HX-Boosted`, `HX-History-Restore-Request` — view behavior differs per class (`is_htmx_partial`).

## Checklist (before claiming fixed)

- [ ] Root cause identified and explained
- [ ] Reproduction test passes
- [ ] Affected test module(s) pass individually (`--keepdb`)
- [ ] `uv run ruff check .` clean
- [ ] Docker image rebuilt for template/static changes; live-verified

## Red Flags

Stop if you're thinking: "quick fix now, investigate later", "one more attempt" (after 3+ failures), "this should work" (without knowing why). Three consecutive failed fixes = architectural problem — stop and discuss with the user.
