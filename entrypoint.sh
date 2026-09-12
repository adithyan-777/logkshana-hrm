#!/bin/sh
# Shared entrypoint for web / celery worker / celery beat.
# Waits for Postgres + Redis, optionally runs tenant migrations + collectstatic
# (only when RUN_MIGRATIONS=1, i.e. the web service), then execs the CMD.
set -e

python - <<'EOF'
import os
import socket
import sys
import time
from urllib.parse import urlparse


def wait_for(host, port, name, timeout=90):
    deadline = time.time() + timeout
    while True:
        try:
            with socket.create_connection((host, int(port)), timeout=5):
                print(f"{name} at {host}:{port} is up", flush=True)
                return
        except OSError:
            if time.time() > deadline:
                sys.exit(f"Timed out waiting for {name} at {host}:{port}")
            time.sleep(2)


wait_for(
    os.environ.get("DB_HOST", "host.docker.internal"),
    os.environ.get("DB_PORT", "5432"),
    "Postgres",
)

broker = urlparse(os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0"))
wait_for(broker.hostname or "redis", broker.port or 6379, "Redis")
EOF

if [ "${RUN_MIGRATIONS:-}" = "1" ]; then
    echo "Running tenant migrations..."
    python manage.py migrate_schemas --noinput
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

# Optional: block until the given public-schema tables exist.
# Used by worker/beat so they never start before web has migrated
# (otherwise beat crash-loops on a fresh deploy).
python - <<'EOF'
import os
import sys
import time

tables = [
    table.strip()
    for table in os.environ.get("WAIT_FOR_TABLES", "").split(",")
    if table.strip()
]
if tables:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.db import connection

    deadline = time.time() + 300
    while True:
        existing = set(connection.introspection.table_names())
        missing = [table for table in tables if table not in existing]
        if not missing:
            print(f"Required tables present: {', '.join(tables)}", flush=True)
            break
        if time.time() > deadline:
            sys.exit(f"Timed out waiting for tables: {', '.join(missing)}")
        time.sleep(3)
EOF

exec "$@"
