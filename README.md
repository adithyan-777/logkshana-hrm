# Pattika

Multi-tenant Django application using [django-tenants](https://django-tenants.readthedocs.io/). Each company gets its own PostgreSQL schema, with shared data (tenants, domains) stored in the public schema.

## Stack

- Python 3.14+
- Django 6.1
- PostgreSQL
- [uv](https://docs.astral.sh/uv/) for dependency management

## Project structure

```
pattika/
├── config/          # Django project settings and URLs
├── companies/       # Shared app — tenant (Company) and domain models
├── employees/       # Tenant-specific app
├── manage.py
└── pyproject.toml
```

| App | Schema | Purpose |
|-----|--------|---------|
| `companies` | Public (shared) | `Company` tenant and `Domain` routing |
| `employees` | Per-tenant | Tenant-scoped business logic |

## Prerequisites

- Python 3.14+
- PostgreSQL 14+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Setup

### 1. Clone and install dependencies

```bash
git clone git@github.com:adithyan-777/pattika.git
cd pattika
uv sync
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
DB_NAME=pattika
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432
```

### 3. Create the database

```bash
createdb pattika
```

### 4. Run migrations

django-tenants uses `migrate` to apply shared migrations on the public schema, then tenant migrations on each company schema.

```bash
uv run manage.py migrate
```

If you add or change models in `companies`, create migrations first:

```bash
uv run manage.py makemigrations companies
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

This creates a `Company` record, its PostgreSQL schema, and a domain for routing requests.

### 7. Run the development server

```bash
uv run manage.py runserver
```

## Common commands

| Command | Description |
|---------|-------------|
| `uv run manage.py migrate` | Migrate public schema and all tenant schemas |
| `uv run manage.py migrate --shared` | Migrate only the public (shared) schema |
| `uv run manage.py migrate --tenant` | Migrate only tenant schemas |
| `uv run manage.py create_tenant` | Interactively create a new company tenant |
| `uv run manage.py list_tenants` | List all registered tenants |
| `uv run manage.py collectstatic` | Collect CSS/JS into `staticfiles/` for production |

## How multi-tenancy works

- **Public schema** holds shared tables: `companies_company`, `companies_domain`, and Django auth/admin tables.
- **Tenant schemas** are created automatically when a `Company` is saved (`auto_create_schema = True`).
- Requests are routed to the correct tenant via the `Domain` model and `TenantMainMiddleware`.
- `SHARED_APPS` run on the public schema; `TENANT_APPS` run on each tenant schema.

## Development notes

- Tenant model: `companies.Company`
- Domain model: `companies.Domain`
- Database engine: `django_tenants.postgresql_backend`
- Environment variables are loaded via `python-dotenv` in `config/settings.py`
