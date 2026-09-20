# ITTISAL HRMS

Multi-tenant HR and attendance system built with Django. Each company gets its own PostgreSQL schema via [django-tenants](https://django-tenants.readthedocs.io/); shared identity and tenant routing live in the public schema.

**UI brand:** ITTISAL HRMS · **Package name:** `pattika` (see `pyproject.toml`)

## Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.14+ |
| Framework | Django 6.0.x (`>=6.0,<6.1`) |
| API | Django REST Framework (gateway / integrations) |
| Database | PostgreSQL 14+ (`django-tenants` schemas) |
| Auth | django-allauth + `django-tenant-users` |
| Jobs | Celery + Redis + django-celery-beat/results |
| Feature flags | django-waffle |
| Frontend | Django templates, HTMX, Alpine.js, Chart.js, Flatpickr, DataTables |
| Deploy | Docker, Gunicorn, WhiteNoise, nginx |
| Tooling | [uv](https://docs.astral.sh/uv/), Ruff, Sentry |

## Project structure

```
logkshana-hrm/
├── config/          # Settings, URLs, navigation, Celery
├── companies/       # Public schema — Company tenant + Domain
├── users/           # Public schema — TenantUser model
├── employees/       # Tenant — people, roles, permissions
├── attendance/      # Tenant — punches, daily, corrections, rules
├── leave/           # Tenant — types, policies, requests, holidays
├── schedule/        # Tenant — timetables, shifts, assignments
├── reports/         # Tenant — report views + exports
├── dashboard/       # Tenant — home KPIs + charts
├── common/          # Shared helpers (pagination, HTMX utils)
├── templates/       # Server-rendered UI
├── static/          # CSS design system, JS, brand assets
├── docs/            # Product + engineering docs
├── manage.py
└── pyproject.toml
```

| App | Schema | Purpose |
|-----|--------|---------|
| `companies`, `users` | Public | Tenants, domains, login identity |
| `employees`, `attendance`, `leave`, `schedule`, `reports`, `dashboard` | Per-tenant | HR business data |

## Frontend (summary)

- **Shell:** `templates/base.html` — sidebar + `#spa-view` (HTMX boost) + Alpine chrome
- **Tokens:** `static/css/tokens.css` — primary accent `#8A1538`, light/dark
- **Brand:** `static/brand/hrms-wordmark.svg`, `static/brand/icon.svg` (favicon)
- **Date/time:** Flatpickr (themed) — Clear / Today / Done; see `static/js/date-picker.js`
- **Prefs:** Theme customizer — mode, layout, scale, sidebar **default | inset** (also styles the right drawer)

More detail: [docs/README.md](docs/README.md).

## Prerequisites

- Python 3.14+
- PostgreSQL 14+
- Redis (Celery)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd logkshana-hrm
uv sync
```

### 2. Configure environment

Copy `.env.example` to `.env` and set at least:

```env
DB_NAME=pattika
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432
CELERY_BROKER_URL=redis://localhost:6379/0
```

### 3. Create the database

```bash
createdb pattika
```

### 4. Run migrations

```bash
uv run manage.py migrate
```

### 5. Create a superuser (public schema)

```bash
uv run manage.py createsuperuser
```

### 6. Create a tenant

```bash
uv run manage.py create_tenant
```

Creates a `Company`, PostgreSQL schema, and routing `Domain`.

### 7. Run the development server

```bash
uv run manage.py runserver
```

For background jobs (optional locally):

```bash
uv run celery -A config worker -l info
uv run celery -A config beat -l info
```

Or use Docker Compose (web + worker + beat + redis):

```bash
docker compose up --build
```

## Common commands

| Command | Description |
|---------|-------------|
| `uv run manage.py migrate` | Migrate public + all tenant schemas |
| `uv run manage.py migrate --shared` | Public schema only |
| `uv run manage.py migrate --tenant` | Tenant schemas only |
| `uv run manage.py create_tenant` | Create a company tenant |
| `uv run manage.py list_tenants` | List tenants |
| `uv run manage.py collectstatic` | Collect static files for production |
| `uv run manage.py seed_demo_data` | Seed demo HR data into a tenant (never public) |

## Multi-tenancy

- **Public schema:** companies, domains, users, auth/admin, shared Celery/waffle tables
- **Tenant schemas:** created when a `Company` is saved (`auto_create_schema = True`)
- **Routing:** `Domain` + `TenantMainMiddleware`
- **Access:** `TenantAccessMiddleware` (django-tenant-users)

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/README.md](docs/README.md) | Doc index |
| [docs/frontend-features.md](docs/frontend-features.md) | Product / IA |
| [docs/frontend-handoff.md](docs/frontend-handoff.md) | CSS, forms, tables |
| [docs/alpine-spa.md](docs/alpine-spa.md) | HTMX + Alpine SPA shell |
| [docs/ui-shell-plan.md](docs/ui-shell-plan.md) | Sidebar shell history |
| [docs/backend-roadmap.md](docs/backend-roadmap.md) | Backend priorities |

## Development notes

- Tenant model: `companies.Company`
- Domain model: `companies.Domain`
- User model: `users.TenantUser`
- Database engine: `django_tenants.postgresql_backend`
- Env loading: `python-dotenv` in `config/settings.py`
