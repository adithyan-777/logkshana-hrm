#!/usr/bin/env bash
# Carry selected legacy rows (employees, punches, devices, schedules)
# into the current schema, as declared in carry_manifest.json.
#
# Flow: dump -> scratch DB -> JSON files (saved separately, inspectable)
#       -> load into target tenant -> heal attendance -> verify report.
#
# Usage (repo root):
#   ./carry-legacy.sh <dump-file> <target-tenant-schema> [carry-dir]
#
# Examples:
#   ./carry-legacy.sh ~/pattika3.dump demo ./carry_data
#   ./carry-legacy.sh ~/pattika3.dump demo          # carry_data/ default
#
# Prereqs: docker (for version-matched pg_restore), target tenant already
# created + migrated. Reads RDS credentials from .env (parsed, never sourced).
set -euo pipefail
cd "$(dirname "$0")"

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <dump-file> <target-tenant-schema> [carry-dir]" >&2
    exit 2
fi
DUMP_FILE="$1"
TENANT="$2"
CARRY_DIR="${3:-./carry_data}"

[[ -f "$DUMP_FILE" ]] || { echo "Dump not found: $DUMP_FILE" >&2; exit 2; }
[[ -f ".env" ]] || { echo "No .env in repo root" >&2; exit 2; }

# Same safe parser as rds-fresh-db.sh: never source the env file.
load_env_file() {
    local file="$1" line key value
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        [[ "$line" =~ ^[[:space:]]*$ ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" =~ ^[[:space:]]*export[[:space:]]+ ]] && \
            line="${line#*export}" && line="${line#"${line%%[![:space:]]*}"}"
        [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
        key="${BASH_REMATCH[1]}"
        value="${BASH_REMATCH[2]}"
        if [[ "${value:0:1}" == '"' && "${value: -1}" == '"' && ${#value} -ge 2 ]]; then
            value="${value:1:-1}"
        elif [[ "${value:0:1}" == "'" && "${value: -1}" == "'" && ${#value} -ge 2 ]]; then
            value="${value:1:-1}"
        else
            [[ "$value" =~ ^(.*[^[:space:]])[[:space:]]+\#.*$ ]] && value="${BASH_REMATCH[1]}"
        fi
        printf -v "$key" '%s' "$value"
        export "$key"
    done < "$file"
}
load_env_file .env

for var in DB_HOST DB_PORT DB_USER DB_PASSWORD; do
    [[ -n "${!var:-}" ]] || { echo "Missing $var in .env" >&2; exit 2; }
done
export PGPASSWORD="$DB_PASSWORD"

SCRATCH="carry_src_$(date +%Y%m%d%H%M%S)"
PG_MAJOR=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tA -c "SHOW server_version_num;" | cut -c1-2)
PG_IMAGE="postgres:${PG_MAJOR}-alpine"
echo "Pulling $PG_IMAGE for version-matched restore..."
docker pull "$PG_IMAGE" >/dev/null || { echo "Could not pull $PG_IMAGE" >&2; exit 1; }

DUMP_ABS="$(cd "$(dirname "$DUMP_FILE")" && pwd)/$(basename "$DUMP_FILE")"
PSQL="psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -v ON_ERROR_STOP=1 -tA"

# pg_restore runs in a throwaway container; plain "localhost" means the
# container itself there, so translate to the host gateway (remote
# endpoints such as RDS pass through untouched).
RESTORE_DB_HOST="$DB_HOST"
RESTORE_GATEWAY_ARGS=()
if [[ "$DB_HOST" == "localhost" || "$DB_HOST" == "127.0.0.1" ]]; then
    RESTORE_DB_HOST="host.docker.internal"
    RESTORE_GATEWAY_ARGS=(--add-host=host.docker.internal:host-gateway)
fi

echo "== Restoring dump into scratch DB $SCRATCH (source untouched)"
$PSQL -c "CREATE DATABASE $SCRATCH OWNER \"$DB_USER\";"
docker run --rm "${RESTORE_GATEWAY_ARGS[@]}" \
    -e "PGPASSWORD=$DB_PASSWORD" \
    -v "$DUMP_ABS:/src.dump:ro" \
    "$PG_IMAGE" pg_restore -h "$RESTORE_DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$SCRATCH" --no-owner /src.dump

echo "== Exporting selected rows to $CARRY_DIR"
mkdir -p "$CARRY_DIR"
CARRY_ABS="$(cd "$CARRY_DIR" && pwd)"
docker compose up -d redis >/dev/null 2>&1 || true
docker compose run --rm -e RUN_MIGRATIONS=0 \
    -v "$CARRY_ABS:/carry_data" \
    web python manage.py carry_legacy_data --step export \
    --scratch-db "$SCRATCH" --src-host "$RESTORE_DB_HOST" --src-port "$DB_PORT" \
    --src-user "$DB_USER" --src-password "$DB_PASSWORD" --out-dir /carry_data
echo "Saved separately under $CARRY_DIR (inspect before loading)."

echo "== Loading into tenant $TENANT (dry run first)"
docker compose run --rm -e RUN_MIGRATIONS=0 \
    -v "$CARRY_ABS:/carry_data" \
    web python manage.py carry_legacy_data --step load \
    --from-dir /carry_data --tenant "$TENANT" --dry-run

echo "== Dropping scratch DB $SCRATCH"
$PSQL -c "DROP DATABASE $SCRATCH;"
echo "Done. Re-run the load step without --dry-run via the Django command when ready."
