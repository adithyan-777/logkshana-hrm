# Project Knowledge — ITTISAL HRMS (`logkshana-hrm`)

> Comprehensive reference for the whole codebase. Generated 2026-09-20 from the
> working tree (which had uncommitted changes at generation time).
> Codebase: Django 6.1 + django-tenants multi-tenant HRMS with HTMX/Alpine frontend.

## 1. Identity (three names — don't get confused)

| Name | Where | Meaning |
|---|---|---|
| `Pattika` | `pyproject.toml`, `README.md`, `docker-compose.yml` (`name: pattika`), DB names | Original repo/project name |
| `ITTISAL HRMS` | Page titles (`base.html`), sidebar brand, `theme.js` (`ittisal-ui-prefs`) | Current product/UI name |
| `logkshana-hrm` | Working directory name | Local folder name |

`README.md` still says "Pattika" and only documents `config/companies/employees` — stale.

## 2. Stack

- Python 3.14+, Django 6.1, PostgreSQL 14+ (per-tenant schemas via `django-tenants`)
- Auth: `django-tenant-users` (`TenantUser`), `django-allauth` (email+username login, optional verification)
- Async: Celery 5 + `django-celery-beat` (DB scheduler) + `django-celery-results`, Redis broker
- API surface: HTML fragments via HTMX (DRF installed but **unused** — zero serializers; `REST_FRAMEWORK` config in `config/settings.py:242` is JSON-only dead config)
- Frontend: HTMX (boosted SPA shell), Alpine.js (3 stores), Chart.js, flatpickr, BoxIcons, Geist Variable font
- Infra: Gunicorn, WhiteNoise (`CompressedStaticFilesStorage`), nginx, Docker Compose, Sentry
- Deps managed with `uv` (`pyproject.toml`, `uv.lock`); lint with `ruff`

## 3. Multi-tenancy architecture

- Tenant model `companies.Company` (`TenantBase`, `auto_create_schema=True`); routing via `companies.Domain` + `TenantMainMiddleware` (first in `MIDDLEWARE`, `config/settings.py:79`), `TenantAccessMiddleware` after auth (`:89`)
- `SHARED_APPS` (`config/settings.py:41`): tenants, admin/auth, `companies`, `users`, allauth, celery beat/results, waffle, DRF
- `TENANT_APPS` (`:62`): `employees`, `schedule`, `leave`, `attendance`, `reports`, `dashboard`
- Tenant models carry **no tenant FK** — isolation is by Postgres schema. Only shared models (`Branch`, `Device`) are cross-schema, referenced via `company__schema_name`
- Celery tenancy discipline: pass `schema_name`, wrap work in `schema_context(public)` → `schema_context(tenant)` (correct in `attendance/tasks.py:17`; **missing** in `employees/tasks.py:21` — known bug)
- Public-schema guards: `seed_demo_data` refuses `--schema=public`, `dashboard/views.py:13` + `config/context_processors.py:60` guard public tenant
- `common` app (abstract models + helpers) is **not** in `INSTALLED_APPS` — works only because all its models are abstract today

## 4. App inventory & URL map

| App | Schema | Models | URLs |
|---|---|---|---|
| `companies` | shared | `Company`, `Branch`, `Domain`, `DeviceBrand`, `DeviceType`, `Device` | `/api/` (`companies/urls.py`: gateway ingest) |
| `users` | shared | `TenantUser` (username unique) | via allauth `/accounts/` + `accounts/profile/` |
| `employees` | tenant | `Department`, `Position`, `Permission`, `Role`, `Area`, `Employee` | `/employees/` CRUD + dept/position/role/permission lists |
| `schedule` | tenant | `Timetable`, `TimetableBreak`, `OvertimeRule`, `Shift`, `ShiftDay`, `ScheduleAssignment`, `TemporarySchedule` | `/schedule/` timetables/shifts/assignments/temporary |
| `leave` | tenant | `LeaveType`, `LeavePolicy`, `LeaveBalance`, `LeaveBalanceTransaction`, `LeaveRequest`, `LeaveApproval`, `Holiday` | `/leave/` types/policies/requests/holidays |
| `attendance` | tenant | `AttendanceTransaction`, `AttendancePeriod`, `DailyAttendance`, `AttendanceCorrection`, `OvertimeRecord`, `AttendanceRule`, `AttendanceCalculationRun` | `/attendance/` transactions/daily/corrections/rules + `my/` + `gateway/` |
| `reports` | tenant | `ReportColumnPreference` only (reads via selectors) | `/reports/` hub + 8 reports + exports + save-columns |
| `dashboard` | tenant | none | `/` index + chart partial |
| `config` | — | none | `/admin/`, `accounts/`, `sentry-debug/` (deliberate 500 — remove in prod) |
| `common` | — | abstract only: `TimeStamped`, `UUID`, `SoftDelete*`, `Audit`, `Base` | helpers: `http.py`, `pagination.py` |

## 5. Backend conventions (HackSoft-style, enforced by `.cursor/skills/django-styleguide/`)

- **Views** parse input → call service/selector → render. No business logic in views. All HTML views: `login_required` + `require_permission(codename)`
- **Services** (`services.py` per app): writes only, `entity_action` naming, keyword-only args, `full_clean()` before `save()`, `@transaction.atomic`, `transaction.on_commit(task.delay())` for Celery
- **Selectors** (`selectors.py`): reads only, own `select_related`/`prefetch_related`; reports has a `selectors/` package (`attendance.py`, `punch_log.py`, `leave.py`, `overtime.py`, `exceptions.py`)
- **Forms**: `form.is_valid()` → `service(**form.cleaned_data)`. Date widgets: `forms.DateInput(attrs={"type": "date"})` (`DATE_INPUT` in attendance/leave/schedule forms), `datetime-local` for punches
- **HTMX helpers** (`common/http.py`): `is_htmx_partial()` (excludes `HX-Boosted` + history-restore — prevents fragment-on-back-button bug), `set_hx_trigger(response, event, toast, close_modal)` emits JSON `HX-Trigger`. Known drift: most CRUD views still emit bare-string `HX-Trigger` (audit issue; tests assert the old strings)
- **Pagination** (`common/pagination.py`, 25/page): CRUD lists use `list_pagination_context` (`pagination_mode="htmx"`); reports use `report_pagination_context` (`reports/utils.py`, `pagination_mode="link"`)
- **RBAC**: `employees/permission_catalog.py` (`PermissionCodename`), `user_permission_codenames(user)`; `nav_can` context gates sidebar/bottombar; reports add self-service scoping (`_self_service_scope`)

## 6. Domain notes

### Attendance (core pipeline)
`AttendanceTransaction` (raw punch: employee, `external_id`, timestamp, direction in/out/unknown, source biometric/web/mobile/manual/import, `raw_data` JSON; index on `(employee, timestamp)`)
→ `AttendancePeriod` (matched IN→OUT) → `DailyAttendance` (per-day status present/absent/late/leave/incomplete + minute counters + `UniqueConstraint` per employee/day)
→ `AttendanceCorrection`, `OvertimeRecord`, `AttendanceRule`, `AttendanceCalculationRun`.
- Ingest: gateway pull (`device_attendance_pull`, `resolve_punch_day` per log) + realtime push (`POST /api/attendancelog/` preferred, `POST /attendance/gateway/` batch) secured by `GATEWAY_SECRET_KEY` shared secret (`attendance/integrations/gateway.py`; empty secret = open — dev only). Match key: device `serial_number` registered + `emp_code == device user_id`
- Self-service: `my_attendance` for own records

### Leave
`LeaveType` (code unique) → `LeavePolicy` (yearly/monthly/no-accrual, entitlement, carry-forward, expiry, min service days) → `LeaveBalance` (unique per employee+policy) + `LeaveBalanceTransaction` ledger → `LeaveRequest` (start/end, approval flow via `LeaveApproval`) + `Holiday` (date + optional end_date)

### Schedule
`Timetable` (normal/flexible, check-in/out windows, cross-day support, grace minutes, `day_change_time`, unique code) + `TimetableBreak` → `Shift` + `ShiftDay` → `ScheduleAssignment` (employee+shift+date range) + `TemporarySchedule` (one-day override). Hot path `schedule/selectors.py:157` `_timetable_for_shift_day` resolves which timetable applies per punch (known N+1 — prefetch `days__timetable`)

### Employees
`Department` (self-parent), `Position`, `Permission` (codename unique), `Role` (M2M permissions, `is_system` guard), `Area` (branch-scoped), `Employee` (`emp_code` indexed **not unique** — known gap; `full_name`, `initials`, `avatar_variant` properties).
- Name avatar: `{% load avatar %}{% avatar employee size="sm" %}` (`employees/templatetags/avatar.py`, registered explicitly in `TEMPLATES[...]["libraries"]`, `config/settings.py:101`) renders `partials/emp_avatar.html` — round initials, deterministic variant 0–7 (md5 of name). Sizes xs–xl. Used in employee list, topbar profile menu, account profile page

### Reports (8)
Hub + attendance summary, punch log, overtime, leave, exceptions, department, individual (+ column prefs + CSV/XLSX/PDF exports). Exports materialize full queryset — unbounded (known OOM risk). Self-service users see only own data

### Dashboard
`dashboard_summary_get()` (`dashboard/selectors.py:48`) → `DashboardSummary` dataclass (headcount, today present/absent/late/leave/incomplete/missing counts, % present, 3 pending queues) + doughnut chart data. Uncached (~4 queries + aggregate per load)

## 7. Frontend system

- **Shell**: `templates/base.html` (`hx-boost`, `#spa-view` retarget in `alpine-app.js:55`, Alpine tree destroy/re-init, progress bar, toasts `aria-live=polite`, mobile bottombar) · `layouts/app_shell.html` · `standalone.html` (login/reset, theme-only script)
- **Alpine stores** (`static/js/alpine-app.js`): `spa` (path/loading/commands/nav), `ui` (menu/command/toasts/modal), `theme` (delegates to theme engine + `toggle()`), `commandPalette` (⌘K)
- **Theme engine** (`static/js/theme.js`, `IttisalTheme` + `LogkshanaTheme` alias): mode `light/dark/system` (default **system**), layout compact/full, scale sm/md/lg, sidebar variant default/inset, mode default/icon/full. Persisted to `ittisal-ui-prefs` (+ legacy `logkshana-*` migration), pre-paint inline script sets `data-theme` (no flash), OS-change listener, `themechange` event → charts re-init. UI: theme customizer (5 segmented radiogroups) + topbar sun/moon quick-toggle
- **Tokens** (`static/css/tokens.css`): `color-scheme: light dark`, `light-dark()` surfaces (`#FAF9F1/#F3F0E7` light; `#262626/#1B1B1B/#383838` dark), peach accent `#e6987e`, semantic colors dark-aware
- **CSS load order** (`partials/stylesheets.html`): tokens → base → motion → layout → sidebar → components (2299 lines, largest) → flatpickr vendor+theme → utilities → compat (Django-widget bridge) → date-picker. `static/css/app.css` is dead legacy (hardcoded `#111827`, unloaded)
- **Date selector** (`static/css/date-picker.css`, native-only per user choice): themed `date/time/datetime-local/month/week` inputs, peach calendar/clock SVG indicators (`#f0b49a` in dark), WebKit segment focus, per-theme `color-scheme` so native popup follows mode
- **Avatar CSS** (`components.css`, `.emp-avatar--0..7` + `.emp-cell` name stack)
- **Charts**: `charts.js` (CSS-var-resolved, `themechange`-aware) + `dashboard-charts.js` (hardcoded palette — ignores dark mode, known issue)
- **Forms pattern**: `non_field_errors → .message.error` + per-field `.error` spans (auth/filter templates use `.form-error`/`.alert` dialect instead — inconsistent, no `aria-invalid` wiring anywhere)

## 8. Static assets

`static/css/`: tokens, base, motion, layout, sidebar, components, utilities, compat, date-picker, flatpickr-theme, main (doc-only `@import` index), vendor/flatpickr.
`static/js/`: theme, alpine-app, app (legacy sidebar toggle), charts, dashboard-charts, date-picker + vendor (htmx, alpine, chart.umd, flatpickr).
`static/brand/`: `icon.svg`, `hrms-wordmark.svg`.

## 9. DevOps & env

- `Dockerfile`: single-stage `python:3.14-slim`, non-root `app` user, gunicorn 3 workers; `collectstatic` at entrypoint (not bake)
- `docker-compose.yml` (`name: pattika`): `redis` (healthchecked), `web/worker/beat` (one image, role CMDs; `DB_HOST: ${CONTAINER_DB_HOST:-${DB_HOST:-host.docker.internal}}` RDS-ready fallback), test-only `db` profile (`:5433`), `nginx` + `certbot` (tools profile), `proxy-net` external network. Beat must never scale past 1
- `entrypoint.sh`: TCP-waits Postgres+Redis, `migrate_schemas` + `collectstatic` only when `RUN_MIGRATIONS=1` (web), `WAIT_FOR_TABLES` gate for worker/beat
- `nginx/conf.d/pattika.conf`: HTTP default, `client_max_body_size 20m`, static 30d immutable; TLS via manual `pattika-ssl.conf.example`
- Env (`.env.example`, 15 keys): `DB_*`, `CONTAINER_DB_HOST`, `CELERY_BROKER_URL`, `TIMEZONE/TIME_ZONE`, `DEVICE_GATEWAY_BASE_URL`, `GATEWAY_SECRET_KEY`, `TENANT_USERS_DOMAIN`, `DEBUG`, `SECURE_COOKIES`. Missing: `SECRET_KEY`, `SENTRY_DSN` (both hardcoded in settings — known issue)
- Timezone default `Asia/Qatar`

## 10. Testing

- 36 files, ~483 tests: attendance 124, employees 130, schedule 80, leave 48, reports 37, companies 31, config 10, dashboard 9, users 8 (login only), common 6. Zero-test apps: none
- Harness: `common/tests/base.py` `BaseTenantTestCase(FastTenantTestCase)` (schema per class, `TenantClient`); service-backed factories (`common/tests/factories.py`); seed guards tested (`test_seed_demo_data`)
- Gaps: `users`/tasks/exports thin; no concurrency/duplicate-punch race test; `OvertimeRecord` only via dashboard KPI
- Run: `.venv\Scripts\python.exe manage.py test <label> --keepdb` (stale `test_pattika_test` DB exists — `--keepdb` required)

## 11. Docs

`docs/`: `frontend-handoff.md` (~1500-line forms/tables/HTMX registry — thorough but dark-mode §743 "light only" now stale), `frontend-features.md`, `backend-roadmap.md` ("current state" §22 stale: claims no Device/Celery), `alpine-spa.md`, `ui-shell-plan.md`. Plus `.cursor/skills/django-styleguide/` (services/selectors rules, high value).

## 12. Audit snapshot (2026-09-20)

Backend 74 · Frontend 79 · Security 45 · DevOps 76 · Quality 78 · Docs 58 → **Overall 68/100** (passable, not prod-ready).
Top fixes: `DeviceType.__str__` crash (`companies/models.py:62` → `self.brand.name`); `employees/tasks.py` ambient-tenant leak; unbounded report exports (`reports/views.py:172…`); hardcoded `SECRET_KEY` + `ALLOWED_HOSTS=["*"]` + `USE_X_FORWARDED_HOST`; empty-secret gateway bypass; `DEBUG` defaults True + Sentry PII@100%; non-unique `emp_code`/`external_id`; `HX-Trigger` JSON/string drift; punch-path N+1; hardcoded doughnut palette.

## 13. Common commands

```bash
.venv\Scripts\python.exe manage.py migrate_schemas --noinput
.venv\Scripts\python.exe manage.py seed_demo_data
.venv\Scripts\python.exe manage.py test employees.tests.test_avatar --keepdb
.venv\Scripts\python.exe manage.py collectstatic --noinput
docker compose up --build redis worker   # phased bring-up; full: up --build
```

## 14. Glossary

- `emp_code` — employee code; device PIN match key (indexed, not unique)
- `external_id` — provider punch ID (service-level dedup, no DB unique)
- `schema_context` — explicit tenant-switch for Celery/shared-model writes
- `nav_can` — per-request permission map gating nav
- `#spa-view` — HTMX swap target for app-shell navigation
- `set_hx_trigger` — canonical JSON list-refresh/toast/modal-close signal
- Gateway — external ZKTeco/biometric service pushing/pulling punches
