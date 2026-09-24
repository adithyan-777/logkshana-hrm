# Alpine.js SPA shell

How the authenticated UI behaves like a single-page app without a separate frontend or REST API.

**Related:** [frontend-features.md](frontend-features.md) · [frontend-handoff.md](frontend-handoff.md) · [ui-shell-plan.md](ui-shell-plan.md)

---

## Why

Pages are full Django HTML responses. HTMX already refreshed **islands** (list search, pagination, add-form posts, dashboard chart). Sidebar clicks used to reload the whole document.

The shell keeps chrome alive and swaps only the page view, using the same Django templates.

---

## What it is (and is not)

| Is | Is not |
|----|--------|
| Server-rendered HTML, Django templates | A React/Vue SPA |
| HTMX boosted links that swap `#spa-view` | Client-side routing with a JSON API |
| Alpine for menus, theme, toasts, modal, command palette | A replacement for list/form HTMX islands |
| Login stays a full page (`standalone.html`) | Alpine required on the sign-in screen |

---

## How navigation works

```
┌─────────────────────────────────────────────────────────┐
│ body  hx-boost → #spa-view                              │
│                                                         │
│  sidebar (stays)     ┌─ #spa-view (swapped) ─────────┐  │
│  command palette     │  topbar (breadcrumbs, menus)  │  │
│  toasts / modal      │  page content                 │  │
│  Chart.js / theme    │  page scripts                 │  │
│  Flatpickr init      └───────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

1. In-app `<a href>` and GET forms inherit `hx-boost` from `<body>`.
2. HTMX requests the **full HTML page**, then selects `#spa-view` and replaces the current one.
3. The URL is pushed (`hx-push-url`).
4. Alpine re-inits the new `#spa-view`, updates the title, and highlights the active sidebar item.
5. `.spa-progress` shows while the swap is in flight.
6. `initDatePickers()` runs on `htmx:afterSettle` so drawer forms get Flatpickr.

Boost target/select is applied in `static/js/alpine-app.js` **only for boosted navigations**. Islands keep their own `hx-target`.

### What must not be boosted

| Action | How |
|--------|-----|
| Log out | `hx-boost="false"` on the profile menu link |
| Report CSV / Excel / PDF | `hx-boost="false"` on export links |
| Login | `standalone.html` (no boost shell) |

---

## Alpine stores

Defined in `static/js/alpine-app.js` on `alpine:init`.

| Store | Role |
|-------|------|
| `$store.spa` | Path, loading flag, command-palette destinations |
| `$store.ui` | Menus, command palette, toasts, modal (drawer) |
| `$store.theme` | Mode, layout, scale, sidebar prefs → `window.IttisalTheme` |

Keyboard: **⌘K / Ctrl+K** palette · **Esc** close · **↑ / ↓ / Enter** in palette

---

## Theme / shell prefs

Persisted in `ittisal-ui-prefs` (legacy `logkshana-*` keys migrated).

| Pref | Values | Effect |
|------|--------|--------|
| `mode` | light / dark / system | `data-theme` |
| `layout` | compact / full | content width |
| `scale` | sm / md / lg | control sizing |
| `sidebarVariant` | **default** / **inset** | Shell gap + **right drawer** shape |
| `sidebarMode` | default / icon / full | Sidebar width |

Brand SVGs go white in dark mode via CSS filter on `.brand-mark` / login wordmark.

---

## Command palette

`templates/partials/command_palette.html` · destinations from `COMMAND_PALETTE` in `config/navigation.py`.

---

## Right drawer (modal)

`templates/partials/modal.html` · Alpine `$store.ui.modalOpen`.

- **default** sidebar variant → edge-flush sheet  
- **inset** → padded, `--r-shell` radius (matches shell)

Backdrop uses shared blur tokens (`--modal-backdrop-filter`).

---

## Backend: boosted vs fragment

Use `common.http.is_htmx_partial(request)`:

| Headers | Meaning | Response |
|---------|---------|----------|
| none | Normal load | Full page |
| `HX-Request` + `HX-Boosted` | SPA navigation | Full page (HTMX selects `#spa-view`) |
| `HX-Request` only | Island | Partial template |

---

## File map

| Path | Role |
|------|------|
| `templates/base.html` | Shell, boost, `#spa-view`, scripts |
| `static/js/alpine-app.js` | Stores, palette, HTMX hooks |
| `static/js/theme.js` | `IttisalTheme` |
| `static/js/date-picker.js` | Flatpickr init + HTMX re-init |
| `static/js/vendor/{htmx,alpine,flatpickr,chart}*` | Vendored libs |
| `static/brand/*` | Logo + favicon |
| `templates/partials/{sidebar,topbar,modal,command_palette,theme_customizer}.html` | Chrome |
| `config/navigation.py` | Breadcrumbs + `COMMAND_PALETTE` |
| `common/http.py` | `is_htmx_partial()` |

Login (`standalone.html`) loads theme + brand only (no Alpine shell).

---

## Adding a new authenticated page

1. Extend `layouts/app_shell.html` (content lands in `#spa-view`).
2. Add breadcrumbs / heading in `config/navigation.py`.
3. Optionally add a `COMMAND_PALETTE` row.
4. Gate fragments with `is_htmx_partial(request)`.
5. Give fragment roots an explicit `hx-target`.
6. Put `hx-boost="false"` on downloads / logout.
7. Date fields are auto-enhanced if they are `input[type=date|datetime-local|time]`.

---

## How to verify

- Sidebar clicks: chrome stays, content + breadcrumbs change, back works
- ⌘K filters and jumps
- List search / pagination still island-scoped
- Drawer forms: Flatpickr opens with Done; submit refreshes list
- Theme prefs persist across SPA navigations
- Log out is a full navigation

Tests: `common.tests.test_http`, `config.tests.test_navigation`, `dashboard.tests.test_dashboard`, boosted list view tests in employees.
