# Agent rules — Pattika / ITTISAL HRMS

Operational rules for coding agents working in this repo. Read before making changes.

> Full architecture reference: `docs/PROJECT-KNOWLEDGE.md`. Style guide: `.cursor/skills/django-styleguide/`.

---

## 1. HTMX / Alpine widget rules

The frontend is an HTMX-boosted SPA (`base.html` has `hx-boost="true"` and `hx-push-url="true"` on `<body>`) + Alpine.js (3 stores in `static/js/alpine-app.js`). These rules exist because each one was observed *actually breaking things* in this codebase.

### 1.1 Django template lexer is single-line (critical)

The lexer only matches `{% … %}`, `{# … #}`, `{{ … }}` when **open and close are on the same line**. A tag spanning lines is silently rendered as *raw source text* in the UI (no error, no 500).

- Every `{% include … with … %}` must be a single (possibly long) line.
- `{# #}` comments: single line only. Multi-line explanation → use `{% comment %} … {% endcomment %}` (tag-level, spans lines legally).
- HTML attributes may wrap (`{{ fmt }}` tokens inside one attribute, and conditionals-hours split across an attribute, are fine as long as each individual `{% … %}` token is on one line).
- Before shipping template edits, scan for multi-line tokens (open without a closer on the same line) — see the scan used for `partials/select.html`.

### 1.2 Swap geometry must match (named-fragment rules)

Page templates serve both a full page and an HTMX fragment via `partialdef` + `template.html#fragment` (views: `render(request, "...", context)` with an `is_htmx_partial(request)` branch, per `common/http.py:8`).

- **The swapped target must be a wrapper element sized exactly like the fragment.** The fragment's top-level node IS the region (`hx-swap="outerHTML"`); never target a *parent* of the fragment or *child* of it — mismatch ⇒ duplicated sections. Piloted on `reports/partials/filter_form.html` targeting `#report-page-region`, present on every `templates/reports/*.html` as the outer div inside the `report_page` partialdef.
- `render_to_string("x.html#name", ctx)` / `get_template("x.html#name")` work for named fragments; `{% include "x.html#frag" %}` works inside fragments — but keep nesting shallow (fragment → include → fragment pattern is proven).
- `{% partialdef %}` bodies hold their own nodelists; fragments render with the full context of the branch that requested them.

### 1.4 The reusable select partial

`templates/partials/select.html` is the standard widget replacing native `<select>`s (single + multi). Partial layout:

- `#select_body` (wrapper resolving DOM `wid` from `uid`, else `"sel-" + name`) → `#select_control` (single markup) and `#select_multi` → `#select_multi_control`. Shared JS: `#select_script` (self-guarding, defines `window.xSelect*` once).
- DOM ids derive from `uid`: `<uid>-search`, `<uid>-list`. **`uid` must be unique per page** — a dup id makes htmx `hx-include="#…"` selectors match multiple widgets (double-`q=` bug).
- POST/GET fidelity: single = hidden `<input>` carries the value; multi = a real hidden `<select multiple>` carries repeated values (forms untouched).
- Multi picks chips/Clear into an external row when `chips_target` is passed (see reports filters); panel stays open for batch picking; `auto_submit` is intentionally ignored in multi mode.
- HTMX option sources: registry `SOURCES` in `common/views.py` (route `select_options`, `?source=…&target=…&selected=…&q=…`), min-2-chars → empty response, permission-gated. New sources = one entry there.
- All widget styling is token-driven in `components.css` (`.x-select*`); dark mode safe by construction — don't hardcode colors.

### 1.5 Alpine integration notes

- Alpine auto-initializes nodes swapped in by htmx; `x-cloak` hides pre-Alpine state (`[x-cloak]` is display:none in base/components CSS).
- Keep `x-data` state minimal (`{open, hi}`) and put command logic in the `window.xSelect*` JS — fragments returned by endpoints contain plain buttons calling those globals, so they work both inline and swapped.
- Keyboard: `@keydown.arrow-down/up.prevent` (list highlight), `@keydown.escape` (close + refocus trigger), `@keydown.enter` (pick highlighted / open when closed).
- `@click.outside` for dismissal; custom `x-select-close` event closes from JS via `dispatchEvent(new CustomEvent(...))` on the root.

### 1.6 Existing patterns to copy instead of inventing

| Task | Copy from |
|---|---|
| Page + fragment from one URL | `reports/views.py` views + `templates/reports/*.html` (`#report_page`) |
| HTMX list-refresh + toast after POST | `common/http.py` `set_hx_trigger` / `is_htmx_partial` usages in `employees/views.py` |
| Searchable options endpoint | `employees/views.py:employee_options_view` and `common/views.py:select_options_view` |
| Drawer/edit forms | `partials/drawer_link.html`, `attendance/daily_edit.html` |
| Reusable parameterized partial | `partials/drawer_link.html`; widgets: `partials/select.html` |
| Auto-apply filters | `templates/reports/partials/filter_form.html` |
| Fragment-endpoint guard redirect + tests | `common/views.py:select_options_view`, `common/tests/test_http.py:SelectOptionsGuardTests` |

---

## 2. Testing rules

- **Always run test files individually, never the whole suite in one command.** Full-suite runs are slow (schema per test class) and bury failures; per-file runs localize breakage.
- Pattern (host venv, connects to local Postgres via `.env`):

  ```bash
  DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m django test reports.tests.test_reports --keepdb
  ```

  - One `app.tests.<module>` per command; repeat per touched app/file.
  - **`--keepdb` is required** — it preserves the test database across runs (schema-per-class setup is the slow part). First run of a module builds it; subsequent runs are fast.
  - Inside the running stack you can also `docker compose exec web python manage.py test <module> --keepdb` (uses the stack's DB).
- After template/view surface changes, sanity-render live through the tenant-client harness (see session pattern: `docker compose … shell` + `TenantClient(company)` + assertions on rendered markers); run the Django-side check *before* shipping the browser to the user.
- For UI verification in Docker: templates/static are baked into the image — `docker compose build web && docker compose up -d web` after each change; then check `http://freshline.localhost:8000/…` (tenant header matters; plain `localhost` 404s with "No tenant").

---

## 3. General repo etiquette (fast pointers)

- Multi-tenants (`freshline`, `demo`, `ittisal`) live in the seeded local DB; tenant-scope changes inside `schema_context(tenant)` — never assume the public schema holds tenant data.
- `common` is NOT an installed app (shareable helpers only, models abstract) — shared *views* there (`common/views.py`) are fine; wire URLs in `config/urls.py`.
- Templates + static are baked in the Docker image; live-editing on host won't reach the running stack without a rebuild.
- Lint with `ruff` before finishing (`uv run ruff check .`).
