# Project logic, naming & ordering audit

Audit of **logkshana-hrm** against HackSoft-style services/selectors and HRM product flow.  
Suggestions only — no code was changed as part of this audit.

**Stack:** Django multi-tenant HRM (`django-tenants` + tenant-users), Alpine + HTMX shell.

---

## Bottom line

CRUD layering (views → services/selectors) is in good shape. Leave naming is the gold standard. Main debt:

1. Attendance naming + **dead duplicate URL routes**
2. **Sidebar active-path bugs** for org/RBAC links
3. **Dual device/punch ingest** endpoints
4. Permission catalog ahead of (or mismatched with) product behavior

Converge attendance and schedule toward the leave naming pattern.

---

## What’s good

- **Tenant split is coherent:** `SHARED_APPS` (tenancy, auth, `companies`, `users`, Celery, waffle) vs `TENANT_APPS` (domain HR apps). `INSTALLED_APPS` correctly unions without double-listing shared apps.
- **Core CRUD apps** (`employees`, `attendance`, `leave`, `schedule`) have models + services + selectors + views + urls + forms; mutations generally go through services.
- **Leave URL/view/service/template naming is the cleanest:** `leave_type_*`, `leave_policy_*`, `leave_request_*`, `holiday_*` align end-to-end.
- **Schedule domain model ↔ service naming** is mostly consistent (`timetable_*`, `shift_*`, `schedule_assignment_*`, `temporary_schedule_*`).
- **Permission catalog** (`employees/permission_catalog.py`) uses clear `module.action` codenames with labels/descriptions.
- **Attendance domain model** documents punch → period → daily → correction/rule clearly in `attendance/models.py`.

---

## 1. App layout

| Location | Apps |
|---|---|
| Project packages | `attendance`, `companies`, `common`, `config`, `dashboard`, `employees`, `leave`, `reports`, `schedule`, `users` (+ `nginx`, `docs`, `static`, `templates`) |
| `SHARED_APPS` | django_tenants, contrib, tenant_users, DRF, **companies**, **users**, allauth, celery beat/results, waffle |
| `TENANT_APPS` | contrib auth/contenttypes, tenant_users.permissions, **employees, schedule, leave, attendance, reports, dashboard** |
| `INSTALLED_APPS` | `SHARED_APPS` + non-overlapping `TENANT_APPS` |

**Notes:** `common` is a shared library (abstract models/http/pagination) — **not** in `INSTALLED_APPS` (OK if abstract-only). `config` is the project package, not an installed app.

---

## 2. Per-domain module presence

| App | models | services | selectors | views | urls | forms | tasks | Notes |
|---|---|---|---|---|---|---|---|---|
| employees | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | + `permission_catalog.py` |
| attendance | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | + `calculation.py`, `integrations/` |
| leave | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | |
| schedule | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | + `calculation.py` |
| reports | ✓ | ✓ | package | ✓ | ✓ | ✓ | ✗ | `selectors/` not `selectors.py`; no admin |
| dashboard | ✗ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | read-only hub — OK |
| companies | ✓ | ✓ | ✓ | stub | ✓ | ✗ | ✗ | `apis.py` is the real interface |
| users | ✓ | ✗ | ✗ | stub | ✗ | ✗ | ✗ | auth via allauth + `config.views.account_profile` |

---

## 3. Service / selector naming mismatches

**Mostly good:** `employee_create`, `attendance_transaction_create`, `leave_request_list`, `dashboard_summary_get`, etc.

| Current | Suggested | Where |
|---|---|---|
| `validate_timetable_times` | `timetable_times_validate` | `schedule/services.py` |
| `resolve_punch_day` | `attendance_punch_day_resolve` | `attendance/services.py` |
| `recalculate_daily_attendance` / `_for_punch` | `daily_attendance_recalculate` / `…_for_punch` | `attendance/services.py` |
| `device_attendance_pull` | `attendance_device_pull` | `attendance/services.py` |
| `attendance_log_create` | `attendance_transaction_ingest` (or move into attendance) | `companies/services.py` |
| `get_preferred_columns` / `save_preferred_columns` | `report_column_preference_get` / `_save` | `reports/services.py` |
| `permission_catalog_ensure` | `permission_ensure_catalog` | `employees/services.py` |
| `employee_role_ensure` | `role_ensure_employee` | `employees/services.py` |
| `employees_assign_employee_role` | `employee_role_assign_default` | `employees/services.py` |
| `companies_ensure_primary_branches` | `company_primary_branches_ensure` | `companies/services.py` |
| `user_is_admin` / `user_has_permission` | OK as `user_*` (entity = user) | `employees/selectors.py` |

Selectors are largely consistent (`*_list`, `*_get`). Reports selectors use `*_report_list` / `punch_log_list` — fine, but “punch” vs model `AttendanceTransaction` is conceptual drift (see §11).

---

## 4–5. URL names vs view names

**Pattern A (preferred, leave-like):** `leave_type_list` → `leave_type_list_view`

**Pattern B (employees):** `employee_list` → `employee_list_view`, but add is `employee_add` (no `_view`)

**Pattern C (attendance — worst):** list/add use `attendance_*` names; edit/delete drop the prefix; dual dead routes.

| URL name | View | Issue |
|---|---|---|
| `attendance_transaction_list` | `transaction_list_view` | URL prefixed; view not |
| `attendance_transaction_add` | `transaction_add` | same |
| `transaction_edit` / `transaction_delete` | `transaction_edit` / `transaction_delete_view` | **no `attendance_` prefix** |
| `daily_attendance_list` | `daily_list_view` | URL full; view short |
| `daily_edit` / `daily_delete` | `daily_edit` / … | inconsistent with list name |
| `correction_edit` vs `attendance_correction_list` | same split | |
| `rule_edit` vs `attendance_rule_list` | same split | |
| `assignment_list` | `assignment_list_view` | model is `ScheduleAssignment`; services use `schedule_assignment_*` |
| `temporary_list` | `temporary_list_view` | model/service `temporary_schedule_*` |
| `attendance-log-create` (kebab) | `AttendanceLogCreateApi` | only kebab name in project |
| `gateway` | `gateway_view` | unprefixed; duplicates API |

**Critical URL bug — `attendance/urls.py`:** each resource registers **two** edit/delete paths that match the **same** path shape (`transactions/<int:...>/edit/`). Django always binds the **first**; the `attendance_transaction_*` / `daily_attendance_*` aliases are unreachable dead code.

**Schedule URL ↔ service drift:** URLs `assignment_*` / `temporary_*` vs services `schedule_assignment_*` / `temporary_schedule_*`.

**Companies API** under `/api/` while UI apps use `/employees/`, `/attendance/`, etc. — fine, but punch ingest lives in two places (below).

---

## 6. Navigation / sidebar order

**Sidebar** (`templates/partials/sidebar.html`): Dashboard → Employees → Attendance → Leave → Schedule → Reports → **Departments → Positions → Roles → Permissions**

**Logical HRM flow issues:**

1. Org/RBAC items are siblings *after* Reports, not under People — clutters primary flow.
2. **Active-state path checks are wrong** for those four: they test `/departments/`, `/positions/`, `/roles/`, `/permissions/` but real paths are under `/employees/…` (e.g. `/employees/departments/`). Active highlighting never works.
3. Leave sidebar lands on **Requests**; leave tabs order Types → Policies → Requests → Holidays (config before ops). Fine for daily use, inconsistent with tab order.
4. Schedule lands on **Timetables** (config-first) — consistent with tabs; good.
5. `SECTIONS` in `config/navigation.py` only has leave/schedule/reports — **missing** employees & attendance for `active_section`.
6. Breadcrumbs/headings cover list/add for most entities but **almost no `*_edit` / `*_delete`** entries (only `employee_edit`).

**Suggested primary nav order:** Dashboard → People (Employees + org/RBAC) → Schedule → Attendance → Leave → Reports.

---

## 7. Model `Meta.ordering`

| Model | Ordering | Note |
|---|---|---|
| `AttendanceTransaction` | `-timestamp` | Good |
| `DailyAttendance` | `-date` | Good |
| `AttendancePeriod` | `["check_in"]` | **Odd** — orders by FK id, not time |
| `Employee`, Branch, Device* | `-id` | Newest-first; directories often want `name` / `emp_code` |
| Department, Position, Role, Permission, Area | none | Unstable list order |
| Timetable, Shift, ScheduleAssignment | none | Same |
| AttendanceCorrection, OvertimeRecord, AttendanceRule, AttendanceCalculationRun | none / Meta only | Same |
| LeaveType/Policy | `name` | Good |
| LeaveRequest | `-start_date` | Good |
| Holiday / TemporarySchedule | `date` | Good |

---

## 8. Permission catalog

- Codenames are consistent (`employees.view`, `attendance.rules.manage`, …).
- **Gaps / logic mismatches:**
  - `DEPARTMENTS_EDIT` / `POSITIONS_EDIT` missing — **edit reuses `*_ADD`** (`employees/views.py`).
  - No `roles.edit` / `roles.delete` / `permissions.edit|delete` — and **no edit/delete URLs/views** for Role/Permission.
  - `LEAVE_APPROVE` exists but **no approve service/view** wired (models have approval status only).
  - No granular `schedule.edit` (only view/add/delete).
  - Attendance edit gated by `ATTENDANCE_ADD` (same pattern as dept edit).

---

## 9. Templates vs URL/view names

| Domain | Template style | Alignment |
|---|---|---|
| leave | `leave_type_list.html` | Matches URL names |
| schedule | `assignment_list.html`, `temporary_list.html` | Matches short URL names, not model names |
| attendance | `transaction_*.html` , `daily_*.html` | Matches **short** view names, not `attendance_transaction_*` URL names |
| employees | `list.html` / `add.html` / `edit.html` for employee; others prefixed | Employee templates underspecified vs `employee_*` |
| reports | `hub.html`, `department.html`, `individual.html` | Shorter than `report_*` URL names |

---

## 10. Fat views / layering

| Finding | Severity |
|---|---|
| CRUD views mostly thin (form → service/selector) | Good |
| `attendance/views.py` `gateway_view` + `_gateway_push_item` (~110 lines): JSON parse, validation, batch 207 handling — **business orchestration in the view**; should live in a service | Broken layering |
| Dual ingest: `POST /attendance/gateway/` and `POST /api/attendancelog/` both call `companies.services.attendance_log_create` | Overlap / confusion |
| `attendance_log_create` in **companies** creates **tenant** `AttendanceTransaction` — cross-app domain bleed (justified by public Device lookup, but naming/ownership is wrong) | Layering smell |
| `reports/views.py` is large but mostly orchestration of selectors/exports — acceptable; services only cover column prefs | Mild |
| Stub `companies/views.py` / `users/views.py` | Dead placeholders |

---

## 11. Duplicate / overlapping concepts

| Concept | Names in use | Clarity |
|---|---|---|
| Raw punch | UI: “Punches”; model: `AttendanceTransaction`; URLs: `attendance_transaction_*` / `transaction_*`; API: `attendance_log` / `attendancelog`; report: `punch_log` | **Three vocabularies** |
| Day outcome | `DailyAttendance` / `daily_attendance_*` / tab “Daily” | Clear enough |
| Correction | `AttendanceCorrection` / mixed URL prefixes | Mostly clear |
| Device ingest | `attendance_log_create`, `device_attendance_pull`, `gateway_view`, `AttendanceLogCreateApi` | Overlapping entry points |
| Schedule assign | `ScheduleAssignment` vs URL `assignment_*` | Mild |
| Temp override | `TemporarySchedule` vs URL `temporary_*` | Mild |

---

## Critical issues (logic / broken layering)

1. **Dead duplicate attendance edit/delete URL patterns** — second route set never matches (`attendance/urls.py`).
2. **Sidebar active-path bugs** for Departments/Positions/Roles/Permissions (`sidebar.html`).
3. **Dual gateway ingest endpoints** with different auth helpers / payload handling paths — risk of drift.
4. **`LEAVE_APPROVE` permission with no approval workflow** — catalog claims capability the product does not expose.
5. **Department/position edit authorized as ADD** — permission model lies about edit rights.
6. **`AttendancePeriod.Meta.ordering = ["check_in"]`** — likely wrong sort for periods.

---

## Naming inconsistencies (current → suggested)

| Current | Suggested |
|---|---|
| `transaction_edit` / `transaction_delete` | `attendance_transaction_edit` / `attendance_transaction_delete` |
| `daily_edit` / `daily_delete` | `daily_attendance_edit` / `daily_attendance_delete` |
| `correction_edit` / `correction_delete` | `attendance_correction_edit` / `attendance_correction_delete` |
| `rule_edit` / `rule_delete` | `attendance_rule_edit` / `attendance_rule_delete` |
| Views `transaction_*`, `daily_*`, … | `attendance_transaction_*`, `daily_attendance_*`, … |
| `assignment_*` URLs | `schedule_assignment_*` |
| `temporary_*` URLs | `temporary_schedule_*` |
| `attendance-log-create` | `attendance_log_create` (snake) or drop in favor of one gateway |
| `gateway` | `attendance_gateway` (or remove if API is canonical) |
| Templates `transaction_*.html` | `attendance_transaction_*.html` **or** rename URLs to `punch_*` and keep templates |
| Employee `list.html` / `add.html` | `employee_list.html` / `employee_add.html` |
| Reports `department.html` | `department_attendance.html` (match URL) |
| UI “Punches” + model Transaction + API Log | Pick one product term (**punch** recommended) and rename outward |

---

## Ordering issues

| Area | Issue | Suggested |
|---|---|---|
| Sidebar | Org/RBAC after Reports; wrong active paths | Group under People; fix path prefixes |
| Leave tabs vs sidebar entry | Tabs config-first; nav opens Requests | Keep both; document intent or align |
| Attendance tabs | Rules last (OK); edit tabs don’t highlight (only `*_list`/`*_add` in `tabs_attendance.html`) | Include `*_edit` in active checks |
| `SECTIONS` | Incomplete | Add `employees`, `attendance` |
| Meta.ordering | Many list models unordered; Employee `-id`; Period by FK | Prefer `name`/`emp_code`/`date`; Period by related timestamp |
| Command palette Leave group | Requests before Types | Match tab order if desired |

---

## Prioritized recommendations

### P0 — correctness / confusion that bites today

1. Collapse attendance edit/delete to **one** URL name set; delete unreachable duplicates.
2. Fix sidebar `slice`/path active checks for `/employees/departments|positions|roles|permissions/`.
3. Choose a single device-ingest surface (`/api/…` **or** `/attendance/gateway/`) and one service owner (prefer `attendance`).
4. Align permission reality: either add `*.edit` codenames or stop calling edit “add”; implement or remove `LEAVE_APPROVE`.
5. Fix `AttendancePeriod.Meta.ordering`.
6. Move gateway orchestration from `attendance.views` into `attendance.services`.

### P1 — consistency that slows every change

5. Standardize URL names: `{entity}_{action}` everywhere; attendance edit/delete get full prefixes.
6. Align views with URL names (`attendance_transaction_list_view`, etc.).
7. Rename schedule URLs to `schedule_assignment_*` / `temporary_schedule_*` **or** shorten services to match URLs — pick one.
8. Unify punch vocabulary (product language vs model vs API).
9. Fix `AttendancePeriod` ordering; add sensible `Meta.ordering` for Department/Position/Role/Timetable/Shift/etc.
10. Move gateway orchestration from `attendance.views` into `attendance.services` (if not done in P0).

### P2 — polish / structure

11. Reorder sidebar: People → Schedule → Attendance → Leave → Reports; nest org/RBAC under Employees.
12. Rename employee/report templates to match URL names; extend breadcrumbs for all `*_edit`.
13. Rename report services to `entity_action`; register `common` only if you need non-abstract models.
14. Add Role/Permission edit/delete (or explicitly mark create-only in UI).
15. Fill `SECTIONS` / tab active states for edit routes; remove stub views or wire them.

---

## Recommended next step

Start with **P0 items 1–2** (dead attendance URLs + sidebar paths) — small, high confidence, no product debate. Then decide punch vocabulary + single gateway before a larger rename pass.

---

*Source: consistency audit of the repository. Companion canvas: Project logic, naming & ordering.*
