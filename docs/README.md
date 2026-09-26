# ITTISAL HRMS — Docs

Engineering and product documentation for this repo.

| Document | Audience | Contents |
|----------|----------|----------|
| [frontend-features.md](frontend-features.md) | Product / UX / FE | What the app does, navigation, feature areas |
| [frontend-handoff.md](frontend-handoff.md) | Frontend | Design tokens, CSS architecture, forms, tables, DataTables |
| [alpine-spa.md](alpine-spa.md) | Frontend / full-stack | HTMX boost + Alpine stores, command palette, partials |
| [ui-shell-plan.md](ui-shell-plan.md) | Historical | Sidebar shell migration (phases 1–3 complete) |
| [backend-roadmap.md](backend-roadmap.md) | Backend | Identity, RBAC, waffle, background-jobs / devices priorities |

Root [README.md](../README.md) covers setup, stack, and common commands.

## Current UI stack (quick)

- Django templates + HTMX (`hx-boost` → `#spa-view`) + Alpine.js
- Design tokens: `static/css/tokens.css` (accent `#8A1538`)
- CSS modules: `base`, `layout`, `sidebar`, `components`, `compat`, `date-picker`, `flatpickr-theme`
- Brand: `static/brand/hrms-wordmark.svg`, `static/brand/icon.svg`
- Date/time: Flatpickr via `static/js/date-picker.js` (Clear / Today / Done)
- Charts: Chart.js · Tables: DataTables · Icons: Boxicons · Font: Geist Variable
