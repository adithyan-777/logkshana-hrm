#!/usr/bin/env bash
# Seed a tenant with an owner/user plus demo employees and HR data.
# Idempotent: safe to re-run (existing owner/company/employees are reused).
#
# Usage:
#   ./seed-demo-tenant.sh [schema] [owner-email] [owner-password]
#
# Examples:
#   ./seed-demo-tenant.sh
#   ./seed-demo-tenant.sh demo demo.owner@example.com 'ChangeMe123!'
#   RESET_OWNER_PASSWORD=1 ./seed-demo-tenant.sh demo demo.owner@example.com 'NewPass123!'
#
# On the server (docker):
#   docker compose exec web python manage.py shell ... (see below) OR
#   copy this file over / pull it with git, then run it inside the container:
#   docker compose exec web bash seed-demo-tenant.sh demo demo.owner@example.com 'ChangeMe123!'
set -euo pipefail
cd "$(dirname "$0")"

SCHEMA="${1:-demo}"
OWNER_EMAIL="${2:-demo.owner@example.com}"
OWNER_PASSWORD="${3:-ChangeMe123!}"

# Pick an interpreter: plain `python` (docker image) or the local venv.
if [ -z "${PYTHON:-}" ]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON=python
  elif [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
  else
    PYTHON=python3
  fi
fi

SCHEMA="$SCHEMA" OWNER_EMAIL="$OWNER_EMAIL" OWNER_PASSWORD="$OWNER_PASSWORD" \
RESET_OWNER_PASSWORD="${RESET_OWNER_PASSWORD:-0}" "$PYTHON" manage.py shell <<'EOF'
import os
from datetime import date

from django.contrib.auth import get_user_model
from django_tenants.utils import get_public_schema_name, schema_context

from companies.models import Company

schema_name = os.environ["SCHEMA"]
email = os.environ["OWNER_EMAIL"]
password = os.environ["OWNER_PASSWORD"]
reset_password = os.environ.get("RESET_OWNER_PASSWORD", "0") == "1"

User = get_user_model()
username = (email.split("@")[0] or "owner").strip() or "owner"

with schema_context(get_public_schema_name()):
    owner, created = User.objects.get_or_create(
        username=username, defaults={"email": email}
    )
    if created or reset_password:
        owner.set_password(password)
        owner.save(update_fields=["password"])
        print(f"owner '{username}': password set")
    else:
        print(f"owner '{username}': exists, password unchanged")

    company, company_created = Company.objects.get_or_create(
        schema_name=schema_name,
        defaults={
            "name": f"{schema_name.title()} Company",
            "paid_until": date(2099, 1, 1),
            "on_trial": True,
            "owner": owner,
        },
    )
    # Saving a new Company auto-creates + migrates its schema.
    print(
        f"tenant '{schema_name}': "
        f"{'created' if company_created else 'already exists'}"
    )
EOF

"$PYTHON" manage.py seed_demo_data \
    --schema "$SCHEMA" \
    --owner-email "$OWNER_EMAIL" \
    --owner-password "$OWNER_PASSWORD"
