# UI Shell Plan — Sidebar Dashboard Layout

> **Status:** Phases 1–3 are **complete**. The live shell is `templates/base.html` + Alpine/HTMX SPA behavior ([alpine-spa.md](alpine-spa.md)). This doc remains as migration history and Phase 4 ideas.

## Goal

Replace the flat horizontal `app_nav.html` with a full app shell: sidebar, top header, and main content. Dashboard remains home at `/`.

---

## Phase 1 — Shell foundation

**Status: complete**

| Item | Path (current) |
|------|----------------|
| App shell | `templates/base.html` + `layouts/app_shell.html` |
| Sidebar | `templates/partials/sidebar.html` |
| Topbar | `templates/partials/topbar.html` |
| CSS | `static/css/{tokens,layout,sidebar,components}.css` |

### Acceptance criteria

- [x] Sidebar sections: Dashboard, Employees, Attendance, Leave, Schedule, Reports
- [x] Active link highlights
- [x] Mobile hamburger / drawer
- [x] Login stays standalone
- [x] HTMX list behavior preserved

---

## Phase 2 — Full page migration

**Status: complete**

- [x] Authenticated pages in the shell
- [x] `app_nav.html` removed from active templates
- [x] Profile in shell

---

## Phase 3 — Polish and navigation UX

**Status: complete**

- [x] Breadcrumbs (`config/navigation.py`)
- [x] Page head actions (Add … → drawer)
- [x] CSS modules + `{% static %}`
- [x] Sidebar modes (default / icon / full) + localStorage (`ittisal-ui-prefs`)
- [x] SPA navigations (HTMX boost + Alpine) — see [alpine-spa.md](alpine-spa.md)
- [x] Theme customizer; sidebar **default | inset** also styles the right drawer
- [x] Brand assets + accent `#8A1538`

---

## Phase 4 — Optional enhancements

**Objective:** Operational dashboards and role-aware UI.

### Tasks

1. **Sidebar badges** — pending leave / corrections counts
2. **Context processor** — inject `nav_summary` for badge counts
3. **Section permissions** — hide links for restricted roles
4. **Dashboard widgets** — richer approval / exception tables
5. **Settings section** — company/tenant config UI

### Acceptance criteria

- [ ] Badges update without extra per-view context
- [ ] Dashboard actionable without leaving home
- [ ] Nav respects RBAC / waffle switches

---

## Current template hierarchy

```
base.html                          ← SPA shell, brand, scripts
├── standalone.html                ← login / password / public gate
├── layouts/app_shell.html         ← page chrome blocks inside #spa-view
├── partials/sidebar.html
├── partials/topbar.html
├── partials/modal.html            ← right drawer
├── partials/command_palette.html
└── app page templates
```

## Sidebar information architecture

| Section | Links |
|---------|-------|
| Overview | Dashboard |
| Employees | Employees, departments, positions, roles, permissions |
| Attendance | Punches, Daily, Corrections, Rules |
| Leave | Types, Policies, Requests, Holidays |
| Schedule | Timetables, Shifts, Assignments, Temporary |
| Reports | Hub + report pages |
| Chrome | Profile, theme, notifications, log out |
