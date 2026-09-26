#!/bin/sh
# Shared entrypoint for web / qcluster.
# Waits for Postgres + Redis, optionally runs tenant migrations + collectstatic
# (only when RUN_MIGRATIONS=1, i.e. the web service), then execs the CMD.
set -e

# Inside containers, plain "localhost" means the container itself, not the
# host or a sibling service. Host-side .env files commonly use
# DB_HOST=localhost / REDIS_HOST=localhost for local processes, which would
# break inside Docker. Translate those to the container-reachable
# equivalents and export so Django sees them.
if [ "${DB_HOST:-}" = "localhost" ] || [ "${DB_HOST:-}" = "127.0.0.1" ]; then
    export DB_HOST="host.docker.internal"
    echo "entrypoint: DB_HOST was localhost, using host.docker.internal" >&2
fi
if [ "${REDIS_HOST:-}" = "localhost" ] || [ "${REDIS_HOST:-}" = "127.0.0.1" ]; then
    # "localhost" is only wrong when this process runs in a container *with*
    # a sibling redis service; local processes never run this script.
    # Compose already sets REDIS_HOST=redis, so this is just a safety net.
    export REDIS_HOST="redis"
    echo "entrypoint: REDIS_HOST was localhost, using redis" >&2
fi

python - <<'EOF'
import os
import socket
import sys
import time


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

wait_for(
    os.environ.get("REDIS_HOST", "redis"),
    os.environ.get("REDIS_PORT", "6379"),
    "Redis",
)
EOF

if [ "${RUN_MIGRATIONS:-}" = "1" ]; then
    echo "Running tenant migrations..."
    python manage.py migrate_schemas --noinput
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

# Optional: block until the given public-schema tables exist.
# Used by qcluster so it never starts before web has migrated.
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
