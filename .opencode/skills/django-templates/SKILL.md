---
name: django-templates
description: Django template patterns — inheritance, partials, Django partialdef fragments, custom tags/filters, and repo layout. Use when creating or editing templates, reusable components, page/fragment rendering, or template tags in the Pattika/ITTISAL HRMS repo or any Django project.
---

# Django Template Patterns

> In this repo (pattika), `AGENTS.md` is always loaded and **wins on conflicts** —
> especially its HTMX rules (§1.1 single-line lexer, §1.2 fragment swap geometry).

## In this repo

- Layout is project-root `templates/`: `base.html`, `layouts/app_shell.html`, `templates/partials/` (shared widgets), `templates/<app>/…` (app pages), `templates/<app>/partials/…` (app-shared fragments).
- **Page + HTMX fragment are served from ONE file** via `{% partialdef name inline %}` blocks; views branch on `common.http.is_htmx_partial(request)` and render `"app/page.html#partial_name"` (pattern: `templates/reports/*.html` + `reports/views.py` extra). Pages extend `layouts/app_shell.html` with `title` / `page_content` blocks.
- **Swap target must be a wrapper sized exactly like the fragment** (`hx-swap="outerHTML"`, fragment's top node IS the region — `#report-page-region` pattern). Never target a parent or child of the fragment.
- **Django template lexer is single-line**: `{% … %}`, `{{ … }}`, `{# … #}` must open and close on the same line; long partials stay inline (single long line); multi-line prose goes in `{% comment %} … {% endcomment %}`.
- Styling is token-driven (`components.css`); dark-mode safe by construction — don't hardcode colors.
- Templates+static are baked into the Docker image: `docker compose build web && docker compose up -d web` to verify live at `http://freshline.localhost:8000/…` (tenant header matters).
- Custom tags live in `<app>/templatetags/<app>_tags.py` (pattern: `reports/templatetags/report_tags.py`).

## Template Inheritance (general)

Three levels: `base.html` (site skeleton) → section/intermediate templates → page templates. Standard blocks in the root: `title`, `content`/`page_content`, `extra_css`, `extra_js`; use `{{ block.super }}` to append.

## Partials and Components (general)

- Partials = fragments included elsewhere: repeated content (pagination, empty states), HTMX responses, DRY-sharing.
- Pass configuration explicitly: `{% include "partials/x.html" with label="…" foo=bar %}`; isolate context with `only` where the fragment must not leak variables.
- One logical component per partial; compose larger UIs from smaller ones.

## Custom Tags and Filters

- `simple_tag` for values (active-nav class, formatting); `inclusion_tag` for rendered fragments; filters for single-value transforms. Create `__init__.py` in the templatetags dir; verify with `{% load … %}` at the top of the using template.

## Anti-Patterns

- Complex conditionals in templates — move to views, model methods, or template tags.
- Hardcoded paths — always `{% url 'route_name' %}`.
- Inline styles / hardcoded colors — token classes only.
- Missing `{% empty %}` on loops that can be empty.
- Adding a page without both the page render and its HTMX branch.
- Multi-line `{% %}`/`{{ }}` tokens (silently renders as raw text — no error).
