---
name: htmx-patterns
description: HTMX patterns for Django — partial/fragment responses, hx-* attributes, response headers (HX-Trigger/HX-Retarget), dynamic UI without JSON. Use when building interactive UI, HTMX endpoints, fragments/swaps, or debugging HX request/response issues in the Pattika/ITTISAL HRMS repo or any Django project.
---

# HTMX Patterns for Django

> In this repo (pattika), **AGENTS.md §1 (HTMX / Alpine widget rules) is the
> source of truth** — it encodes the rules that actually broke this app. This
> skill supplies general HTMX knowledge that AGENTS.md does not repeat.

## In this repo (quick facts)

- HTMX detection: **`is_htmx_partial(request)`** from `common/http.py` — returns True for plain `HX-Request` fragment calls, False for boosted navigation and history-restore requests (which must get the full page).
- Fragments: `{% partialdef %}` blocks in the same template, swapped into wrapper targets sized exactly like the fragment (`hx-swap="outerHTML"`).
- Body-level `hx-boost="true"`, `hx-push-url="true"`, `hx-headers` CSRF token flow from `templates/base.html` — CSRF always included for HTMX forms; **internal (non-navigation) fetches must set `hx-push-url="false"`** or they pollute the address bar/history.
- Toasts/events: `common.http.set_hx_trigger(response, event=…, toast=…)` sets the `HX-Trigger` header (`showToast`, `closeModal` patterns).
- Every fragment-only endpoint must guard non-HTMX visits — pattern `redirect_stale_fragment_visit` in `common/views.py`.
- Alpine integrates nodes swapped by htmx automatically; keep `x-data` minimal and put command logic in global `window.x*` JS so fragments work both inline and swapped; `x-cloak` hides pre-Alpine state.
- Templates+static are baked into the Docker image — rebuild (`docker compose build web && docker compose up -d web`) before checking behavior in the browser; test modules run per-file with `--keepdb`.

## Core Philosophy

- Server renders HTML fragments, not JSON; HTMX requests return partials only (a full `base.html` response to an HTMX call breaks the SPA).
- Progressive enhancement: pages must work without JS.
- Keep client complexity minimal; the server does the heavy lifting.

## UX Utilities

- **Loading indicators**: `hx-indicator` + the widget's `.htmx-indicator` spinner so users always see progress.
- **Feedback**: toasts via `HX-Trigger` (`showToast`), not silent swaps; validation errors re-render the form fragment.
- **Status codes**: 400 for validation, 403/405 where appropriate; HTMX never swallows errors — `htmx:responseError` pages toast "Could not load that page".
- **Duplicate submits**: `hx-disabled-elt="this"` on action buttons.

## Form Handling Pattern

```python
def create_view(request):
    if request.method == "POST":
        form = MyForm(request.POST)
        if form.is_valid():
            obj = form.save()
            if is_htmx_partial(request):
                response = render(request, "app/page.html#row", {"row": obj})
                set_hx_trigger(response, toast="Created.")
                return response
            return redirect("app:list")
        # fall through: re-render form fragment with errors
    ...
```

## Response Headers Reference

| Header | Use |
|---|---|
| `HX-Trigger` | fire client events after the swap (repo: `set_hx_trigger` with toast payloads) |
| `HX-Redirect` | full client redirect after an action |
| `HX-Retarget` / `HX-Reswap` | override target/swap from the server (e.g. route errors to the form) |
| `HX-Refresh` | force a full reload after a major state change |

## Common Pitfalls

- Full-page templates returned to HTMX calls (must return the fragment branch).
- `hx-push-url` inherited from `<body>` onto widget fetches (rule: explicit false per element) — an aux URL like `/select-options/?…` silently replaces the report page in the address bar, and a later refresh replays the fragment URL.
- Fragments rendered as bare pages for non-HTMX visits.
- Swap-geometry mismatches (fragment ↔ target wrapper) multiplying sections.
- Multi-line Django template tokens being silently emitted as raw text.
- N+1 queries in fragment views — `select_related()`/`prefetch_related()` apply to HTMX views too.
- Analyzing HTMX behavior without the browser context (boosted vs fragment vs history-restore request flags change view behavior).

## Integration

- **django-forms**: form fragments + `set_hx_trigger` feedback.
- **django-templates**: `partialdef` fragment organization.
- **systematic-debugging**: root-cause debugging of HTMX flows.
