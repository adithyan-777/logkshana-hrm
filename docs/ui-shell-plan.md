# UI Shell Plan — Sidebar Dashboard Layout

## Goal

Replace the flat horizontal `app_nav.html` with a full app shell: fixed sidebar, top header, and main content area. Dashboard remains the home page at `/`.

---

## Phase 1 — Shell foundation (current)

**Objective:** Prove the layout with minimal migration risk.

### Deliverables

| Item | Path |
|------|------|
| App shell layout | `templates/layouts/app_shell.html` |
| Sidebar nav | `templates/partials/sidebar.html` |
| Top header | inline in `app_shell.html` (`page_title` block) |
| Layout CSS | `templates/base.html` |
| Phase plan | `docs/ui-shell-plan.md` |

### Pages migrated to shell

- Dashboard (`/`)
- Employees list (`/employees/`)
- Attendance punches (`/attendance/transactions/`)
- Leave requests (`/leave/requests/`)
- Reports hub (`/reports/`)

### Pages unchanged (still use `app_nav.html`)

All other list/add/report templates until Phase 2.

### Acceptance criteria

- [x] Sidebar shows grouped sections: Overview, Employees, Attendance, Leave, Schedule, Reports
- [x] Active link highlights on migrated pages
- [x] Mobile: hamburger toggles sidebar overlay
- [x] Login/profile pages stay centered (no sidebar)
- [x] Existing HTMX list behavior unchanged on migrated pages
- [x] Dashboard and view tests pass

---

## Phase 2 — Full page migration

**Status: complete**

**Objective:** Move every authenticated page into the shell; remove flat nav.

### Tasks

1. Migrate remaining **~20 templates** (all list/add/report pages under employees, attendance, leave, schedule, reports)
2. Migrate **account profile** to extend `app_shell.html` (remove inline `page-nav`)
3. Delete or archive `templates/partials/app_nav.html`
4. Remove `{% include "partials/app_nav.html" %}` from `schedule/partials/nav.html` if unused
5. Update tests that assert on old nav markup

### Acceptance criteria

- [x] No template includes `app_nav.html`
- [x] All authenticated routes render inside sidebar shell
- [x] Full test suite passes

---

## Phase 3 — Polish and navigation UX

**Status: complete**

**Objective:** Improve wayfinding and responsive behavior.

### Tasks

1. **Collapsible sidebar sections** — Leave, Schedule, Reports use `<details>` or JS toggle; auto-expand when section is active
2. **Breadcrumbs** in `app_header.html` — e.g. `Dashboard / Attendance / Punches`
3. **Page header actions** — “Add employee”, “Record punch” buttons in header bar on list pages
4. **Extract CSS** to `static/css/app.css` (optional) and use `{% static %}` in base
5. **Sidebar collapse** — icon-only mode (240px → 64px) with localStorage preference
6. Trim dashboard **Quick Links** once sidebar covers all destinations (or keep 3–4 KPI deep-links)

### Acceptance criteria

- [x] Reports sub-nav visible without visiting hub first
- [x] Breadcrumbs accurate on nested pages
- [x] Sidebar usable on mobile and tablet

---

## Phase 4 — Optional enhancements

**Objective:** Operational dashboards and role-aware UI.

### Tasks

1. **Sidebar badges** — pending leave / corrections counts from `dashboard_summary_get`
2. **Context processor** — inject `nav_summary` globally for badge counts
3. **Section permissions** — hide Schedule/Reports links for restricted roles (when auth roles exist)
4. **Dashboard widgets** — recent exceptions, pending approvals table on home page
5. **Settings section** — company/tenant config when `companies` gets UI

### Acceptance criteria

- [ ] Badges update without extra per-view context
- [ ] Dashboard actionable without leaving home page

---

## Template hierarchy (target)

```
base.html
├── account/login.html          (standalone-page)
├── account/profile.html        (app_shell — Phase 2)
└── layouts/app_shell.html
    ├── partials/sidebar.html
    └── page templates (block page_content, page_title)
```

## Sidebar information architecture

| Section | Links |
|---------|-------|
| Overview | Dashboard |
| Employees | Employees, Add employee |
| Attendance | Punches, Daily, Corrections, Rules |
| Leave | Types, Policies, Requests, Holidays |
| Schedule | Timetables, Shifts, Assignments, Temporary |
| Reports | Hub + 7 report pages |
| Footer | Profile, Log out |
