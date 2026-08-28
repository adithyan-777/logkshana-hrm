# Pattika

Django HR and attendance application. Companies, branches, and devices live in the same PostgreSQL database as employees, schedules, leave, and attendance.

## Stack

- Python 3.14+
- Django 6.0
- PostgreSQL
- [uv](https://docs.astral.sh/uv/) for dependency management

## Project structure

```
pattika/
├── config/          # Django project settings and URLs
├── companies/       # Company, branch, and device models
├── employees/       # Employees, departments, roles
├── schedule/        # Timetables and shifts
├── leave/           # Leave types, requests, holidays
├── attendance/      # Punches and daily attendance
├── manage.py
└── pyproject.toml
```

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

If you previously ran this project with django-tenants, create a new database. Tenant schemas are not migrated automatically.

### 4. Run migrations

```bash
uv run manage.py migrate
```

### 5. Create a superuser

```bash
uv run manage.py createsuperuser
```

### 6. Run the development server

```bash
uv run manage.py runserver
```

## Common commands

| Command | Description |
|---------|-------------|
| `uv run manage.py migrate` | Apply database migrations |
| `uv run manage.py createsuperuser` | Create an admin user |
| `uv run manage.py seed_demo_data` | Seed demo HR data |
| `uv run manage.py create_primary_branches` | Create a primary branch for each company |

## Development notes

- Database engine: `django.db.backends.postgresql`
- Environment variables are loaded via `python-dotenv` in `config/settings.py`
