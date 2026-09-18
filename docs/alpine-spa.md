# Alpine.js SPA shell

What changed when Alpine.js was added so the authenticated UI behaves like a single-page app, without a separate frontend or REST API.

**Related:** [frontend-features.md](frontend-features.md) (product / IA), [frontend-handoff.md](frontend-handoff.md) (CSS / markup), [ui-shell-plan.md](ui-shell-plan.md) (sidebar layout history).

---

## Why

Pages were full Django HTML responses. HTMX already refreshed **islands** (list search, pagination, add-form posts, the dashboard chart). Clicking a sidebar or tab still reloaded the whole document: sidebar, topbar, scripts, and theme state all came back from scratch.

This change keeps the chrome alive and swaps only the page view, using the same Django templates.

---

## What it is (and is not)

| Is | Is not |
|----|--------|
| Server-rendered HTML, still Django templates | A React/Vue SPA |
| HTMX boosted links that swap `#spa-view` | Client-side routing with a JSON API |
| Alpine for menus, theme, toasts, modal, command palette | A replacement for existing list/form HTMX |
| Login stays a full page (`standalone.html`) | Alpine on the sign-in screen |

---

## How navigation works

```
┌─────────────────────────────────────────────────────────┐
│ body  hx-boost → #spa-view                              │
│                                                         │
│  sidebar (stays)     ┌─ #spa-view (swapped) ─────────┐  │
│  command palette     │  topbar (breadcrumbs, menus)  │  │
│  toasts / modal      │  page content                 │  │
│  mobile bottom bar   │  extra_js                     │  │
│  Chart.js / theme.js └───────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

1. In-app `<a href>` and GET forms inherit `hx-boost` from `<body>`.
2. HTMX requests the **full HTML page**, then selects `#spa-view` from the response and replaces the current one (`outerHTML`).
3. The URL is pushed (`hx-push-url`), so back/forward still work.
4. Alpine re-inits the new `#spa-view`, updates the document title, and highlights the active sidebar item from `location.pathname`.
5. A thin progress bar (`.spa-progress`) shows while that swap is in flight.

Existing HTMX islands keep their own `hx-target` (for example `#employee-list` or `this`). Those requests are **not** treated as page navigations.

Boost target/select is applied in `static/js/alpine-app.js` **only for boosted link/form navigations**. It is not set on `<body>`, so add-forms, list search, pagination, and post-create table refreshes still receive the fragment HTML as-is. Putting `hx-select="#spa-view"` on `<body>` made those fragments swap to empty (no `#spa-view` in the partial).

### What must not be boosted

| Action | How |
|--------|-----|
| Log out | `hx-boost="false"` on the profile menu link |
| Report CSV / Excel / PDF | `hx-boost="false"` on export links |
| Login | Separate `standalone.html` layout (no boost, no Alpine shell) |

---

## Alpine stores

Defined in `static/js/alpine-app.js` on `alpine:init`.

| Store | Role |
|-------|------|
| `$store.spa` | Current path, loading flag, command-palette destinations |
| `$store.ui` | Open menu (`profile` / `notify` / `theme`), command palette, toasts, modal |
| `$store.theme` | Layout, scale, sidebar prefs — writes through `window.IttisalTheme` |

Chrome that lives **outside** `#spa-view` (sidebar, command palette, toasts, modal, progress bar) keeps Alpine state across page swaps. Topbar menus live **inside** `#spa-view`, so they re-init after each navigation; prefs still come from `$store.theme`.

Keyboard:

- **⌘K / Ctrl+K** — command palette
- **Esc** — close palette, modal, or menus
- **↑ / ↓ / Enter** — move and open a palette result

---

## Command palette

Sidebar search (⌘K) was previously decorative. It now opens `templates/partials/command_palette.html`.

Destinations are declared in `COMMAND_PALETTE` in `config/navigation.py`. The navigation context processor resolves URLs and injects `command_palette` into every authenticated page. Alpine reads `#command-palette-data` (`json_script`).

To add a jump target, append an entry:

```python
{
    "title": "…",
    "subtitle": "…",
    "url_name": "my_url_name",
    "group": "People",
    "icon": "bx-user",
}
```

---

## Backend: boosted vs fragment

Boosted navigations send `HX-Request: true` **and** `HX-Boosted: true`. List/add views used to treat any `HX-Request` as “return the table/form partial,” which would break SPA swaps (`#spa-view` would be missing).

`common.http.is_htmx_partial()` is now the check:

| Headers | Meaning | Response |
|---------|---------|----------|
| none | Normal browser load | Full page |
| `HX-Request` + `HX-Boosted` | SPA page navigation | Full page (HTMX selects `#spa-view`) |
| `HX-Request` only | Search, pagination, form island, chart refresh | Partial template |

Use `is_htmx_partial(request)` in new list/add/report views. Do not go back to a raw `HX-Request` check.

---

## File map

| Path | Change |
|------|--------|
| `templates/base.html` | Alpine + HTMX boost, `#spa-view`, progress bar, toasts, command palette, Chart.js always loaded |
| `static/js/alpine-app.js` | Stores, palette, HTMX ↔ Alpine (initTree, title, nav active, loading) |
| `static/js/theme.js` | `window.IttisalTheme`; storage keys unified to `ittisal-*` |
| `templates/partials/command_palette.html` | Palette UI |
| `templates/partials/sidebar.html` | Search opens palette; `data-nav-match` for active section |
| `templates/partials/profile_menu.html` | Alpine menu; logout not boosted |
| `templates/partials/notifications_menu.html` | Alpine menu |
| `templates/partials/theme_customizer.html` | Alpine + `$store.theme` |
| `templates/partials/modal.html` | Alpine open/close |
| `templates/partials/topbar.html` | Activity toast via `$store.ui` |
| List templates | `hx-target="this"` on post-create refresh islands |
| `templates/dashboard/index.html` | Chart panel `hx-target="this"` |
| `templates/reports/partials/filter_form.html` | Exports `hx-boost="false"` |
| `config/navigation.py` | `COMMAND_PALETTE` + `command_palette_for()` |
| `config/context_processors.py` | Injects `command_palette` |
| `common/http.py` | `is_htmx_partial()` |
| App `views.py` files | Partial rendering uses `is_htmx_partial` |
| `static/js/dashboard-charts.js` | Init on SPA swap, not only `DOMContentLoaded` |
| Removed | `static/js/dropdowns.js`, `static/js/toasts.js` (replaced by Alpine) |

Login (`templates/standalone.html`) still loads `theme.js` only.

---

## Adding a new authenticated page

1. Extend `layouts/app_shell.html` as today. It already sits inside `#spa-view`.
2. Add breadcrumbs / heading in `config/navigation.py`.
3. If it should appear in ⌘K, add a `COMMAND_PALETTE` row.
4. If the view returns an HTMX fragment for search or a form, gate it with `is_htmx_partial(request)`.
5. Give fragment roots an explicit `hx-target` (`#some-id` or `this`) so they do not inherit `hx-target="#spa-view"`.
6. Put `hx-boost="false"` on downloads, external links, and logout.

---

## How to verify

- Click sidebar items: sidebar stays, page content and breadcrumbs change, URL updates, back button works.
- ⌘K (or the sidebar Search row) filters and jumps to a page.
- Employee list search and pagination still swap only the table.
- Apply report filters: full results appear in the main view; CSV/Excel/PDF still download.
- Log out still leaves the app (full navigation).
- Theme customizer still persists across SPA navigations.

Tests covering this:

- `common.tests.test_http` — boosted vs fragment headers
- `config.tests.test_navigation` — palette in the context processor
- `dashboard.tests.test_dashboard` — Alpine / `#spa-view` / palette on the dashboard
- `employees.tests.test_views.test_boosted_list_returns_full_page` — boosted list is a full page, not the table partial
