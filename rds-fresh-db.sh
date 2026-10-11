#!/usr/bin/env bash
# Back up the current RDS database, then build a fresh database on the
# same instance and migrate it from scratch.
#
# The old database is NEVER written to, migrated, or dropped by this
# script. Cutover (repointing the app) is deliberately manual.
#
# Credentials come from the server .env (same file the compose stack
# uses) and are never printed. Override with ENV_FILE=/path/to/.env.
#
# Usage:
#   ./rds-fresh-db.sh <new-db-name> [backup-dir]
#   ./rds-fresh-db.sh --help
#
# Examples:
#   ./rds-fresh-db.sh pattika_fresh ~/backups/pattika
#   ./rds-fresh-db.sh pattika_fresh
#   ENV_FILE=/srv/pattika/.env ./rds-fresh-db.sh pattika_fresh
#
# Flags (must come before positional args):
#   --yes              skip the CREATE DATABASE confirmation prompt
#   --reuse-existing   use <new-db-name> if it already exists (default: abort)
#   --skip-restore-check
#                      skip the restore-into-scratch verification step
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE="${ENV_FILE:-.env}"
YES=0
REUSE_EXISTING=0
SKIP_RESTORE_CHECK=0

usage() {
    sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h) usage 0 ;;
        --yes) YES=1; shift ;;
        --reuse-existing) REUSE_EXISTING=1; shift ;;
        --skip-restore-check) SKIP_RESTORE_CHECK=1; shift ;;
        --*) echo "Unknown flag: $1 (see --help)" >&2; exit 2 ;;
        *) break ;;
    esac
done

if [[ $# -lt 1 ]]; then
    echo "Missing <new-db-name> (see --help)" >&2
    exit 2
fi
NEW_DB="$1"
# Home-based default: /var/backups typically needs root, and this script
# must run as a normal user. $HOME (not ~) so it expands inside quotes.
BACKUP_DIR="${2:-$HOME/backups/pattika}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Env file not found: $ENV_FILE" >&2
    exit 2
fi

# shellcheck disable=SC1090
# NOTE: the env file is parsed, never sourced: values may contain spaces,
# quotes, $, backticks or other shell metacharacters (common in generated
# passwords) that would break or dangerously execute under `source`.
load_env_file() {
    local file="$1" line key value
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Trim leading/trailing whitespace (incl. CRLF).
        line="${line%$'\r'}"
        [[ "$line" =~ ^[[:space:]]*$ ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        # Optional `export ` prefix.
        [[ "$line" =~ ^[[:space:]]*export[[:space:]]+ ]] && \
            line="${line#*export}" && line="${line#"${line%%[![:space:]]*}"}"
        if [[ ! "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            echo "Warning: ignoring non-assignment line in $file: $line" >&2
            continue
        fi
        key="${BASH_REMATCH[1]}"
        value="${BASH_REMATCH[2]}"
        # Strip one layer of matching surrounding quotes. Unquoted values
        # get python-dotenv treatment: a " #" suffix starts a comment.
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
load_env_file "$ENV_FILE"

for var in DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME; do
    if [[ -z "${!var:-}" ]]; then
        echo "Required variable $var is missing from $ENV_FILE" >&2
        exit 2
    fi
done
OLD_DB="$DB_NAME"

if [[ "$NEW_DB" == "$OLD_DB" ]]; then
    echo "Refusing: <new-db-name> must differ from the current DB ($OLD_DB)" >&2
    exit 2
fi
if [[ ! "$NEW_DB" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
    echo "Refusing: '$NEW_DB' is not a safe Postgres identifier" >&2
    exit 2
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
DUMP_FILE="$BACKUP_DIR/${OLD_DB}_${STAMP}.dump"
LOG_FILE="$BACKUP_DIR/run_${STAMP}.log"

log() {
    echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE" >&2
}
die() {
    log "FATAL: $*"
    exit 1
}

for bin in psql pg_dump pg_restore docker; do
    command -v "$bin" >/dev/null 2>&1 || die "Missing required binary: $bin (install postgresql-client / docker)"
done

export PGPASSWORD="$DB_PASSWORD"
PSQL="psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -v ON_ERROR_STOP=1 -tA"

# ------------------------------------------------------------------
# Phase 0 — preflight (read-only).
# ------------------------------------------------------------------
log "Phase 0: preflight against $DB_HOST:$DB_PORT (target old DB: $OLD_DB)"
pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null || die "Postgres not reachable"
$PSQL -c "SELECT version();" | tee -a "$LOG_FILE" >&2
$PSQL -c "SELECT 1 FROM pg_database WHERE datname='$OLD_DB';" | grep -q 1 \
    || die "Database '$OLD_DB' does not exist on $DB_HOST"

BASELINE_FILE="$BACKUP_DIR/baseline_${OLD_DB}_${STAMP}.txt"
{
    echo "# baseline for $OLD_DB @ $STAMP"
    $PSQL -d "$OLD_DB" -c "SELECT pg_size_pretty(pg_database_size('$OLD_DB'));"
    $PSQL -d "$OLD_DB" -c \
        "SELECT schemaname || '.' || tablename || '=' || (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', schemaname, tablename), false, true, '')))[1]::text FROM pg_tables WHERE schemaname NOT LIKE 'pg\_%' AND schemaname <> 'information_schema' ORDER BY 1;"
} > "$BASELINE_FILE"
log "Baseline written to $BASELINE_FILE"

# ------------------------------------------------------------------
# Phase 1 — backup (old DB is only ever read).
# ------------------------------------------------------------------
log "Phase 1: dumping $OLD_DB -> $DUMP_FILE"
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -Fc -f "$DUMP_FILE" "$OLD_DB"
[[ -s "$DUMP_FILE" ]] || die "Dump file is empty"
pg_restore --list "$DUMP_FILE" >/dev/null || die "Dump file failed pg_restore --list"
sha256sum "$DUMP_FILE" | tee -a "$BACKUP_DIR/SHA256SUMS" >&2
log "Dump OK: $(du -h "$DUMP_FILE" | cut -f1)"

if [[ "$SKIP_RESTORE_CHECK" -eq 0 ]]; then
    SCRATCH="${OLD_DB}_restore_check"
    log "Restore verification into scratch DB $SCRATCH"
    $PSQL -c "DROP DATABASE IF EXISTS $SCRATCH;"
    $PSQL -c "CREATE DATABASE $SCRATCH OWNER \"$DB_USER\";"
    pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$SCRATCH" --no-owner "$DUMP_FILE" \
        || die "Restore into scratch DB failed"
    RESTORED_COUNT=$($PSQL -d "$SCRATCH" -c \
        "SELECT count(*) FROM pg_tables WHERE schemaname NOT LIKE 'pg\_%' AND schemaname <> 'information_schema';")
    BASE_COUNT=$(grep -c "=" "$BASELINE_FILE" || true)
    log "Restored tables: $RESTORED_COUNT (baseline entries: $BASE_COUNT)"
    [[ "$RESTORED_COUNT" == "$BASE_COUNT" ]] || die "Table count mismatch after restore"
    $PSQL -c "DROP DATABASE $SCRATCH;"
    log "Restore verification passed; scratch DB dropped"
else
    log "Restore verification SKIPPED (--skip-restore-check)"
fi
log "BACKUP OK: $DUMP_FILE"

# ------------------------------------------------------------------
# Phase 2 — fresh database.
# ------------------------------------------------------------------
if $PSQL -c "SELECT 1 FROM pg_database WHERE datname='$NEW_DB';" | grep -q 1; then
    if [[ "$REUSE_EXISTING" -eq 1 ]]; then
        log "Database $NEW_DB already exists; reusing (--reuse-existing)"
    else
        die "Database '$NEW_DB' already exists (use --reuse-existing to proceed)"
    fi
else
    if [[ "$YES" -eq 0 ]]; then
        echo "About to CREATE DATABASE $NEW_DB on $DB_HOST (old DB $OLD_DB untouched)." >&2
        read -r -p "Type YES to continue: " confirm
        [[ "$confirm" == "YES" ]] || die "Aborted by user"
    fi
    $PSQL -c "CREATE DATABASE $NEW_DB OWNER \"$DB_USER\";"
    log "Created database $NEW_DB"
fi

# ------------------------------------------------------------------
# Phase 3 — migrate the fresh database (explicit target only).
# ------------------------------------------------------------------
log "Phase 3: migrating target DB = $NEW_DB (old DB $OLD_DB is not touched)"
docker compose up -d redis 2>&1 | tee -a "$LOG_FILE" >&2
docker compose run --rm \
    -e RUN_MIGRATIONS=0 \
    -e DB_NAME="$NEW_DB" \
    web python manage.py migrate_schemas --noinput 2>&1 | tee -a "$LOG_FILE" >&2

DC="docker compose run --rm -e RUN_MIGRATIONS=0 -e DB_NAME=$NEW_DB web python manage.py"
UNAPPLIED=$($DC showmigrations 2>/dev/null | grep -cE "\[ \]" || true)
log "Unapplied migrations on $NEW_DB: $UNAPPLIED"
[[ "$UNAPPLIED" == "0" ]] || die "Unapplied migrations remain on $NEW_DB"
$DC check 2>&1 | tee -a "$LOG_FILE" >&2
$DC makemigrations --check --dry-run 2>&1 | tee -a "$LOG_FILE" >&2
log "MIGRATE OK: all migrations applied on $NEW_DB, check clean"

# ------------------------------------------------------------------
# Phase 4 — report. Cutover stays manual.
# ------------------------------------------------------------------
cat >&2 <<EOF
================================================================
DONE. Summary:
  backup:   $DUMP_FILE (verified)
  old DB:   $OLD_DB (untouched, still serving)
  new DB:   $NEW_DB (migrated, empty of business data)
  log:      $LOG_FILE

Manual cutover when ready (NOT done by this script):
  1. Optional seed:  DB_NAME=$NEW_DB docker compose run --rm web bash seed-demo-tenant.sh demo demo.owner@example.com 'ChangeMe123!'
  2. In the server .env set DB_NAME=$NEW_DB, then: docker compose up -d web qcluster
  3. Smoke-test login + one attendance calc.
  Rollback: set DB_NAME back to $OLD_DB (or restore $DUMP_FILE).
================================================================
EOF
