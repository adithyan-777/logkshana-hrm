#!/usr/bin/env bash
# Pull a fresh dump of the server's RDS database to this machine over SSH.
#
# Unlike ./rds-fresh-db.sh this script creates nothing on the server side:
# the server's .env supplies the RDS credentials (loaded remotely, never
# printed, never hardcoded here), pg_dump streams the current data straight
# through the SSH connection, and the result is verified locally.
#
# Usage:
#   ./rds-pull-dump.sh --ssh user@host --remote-dir /path/to/project [backup-dir]
#   ./rds-pull-dump.sh --help
#
# Examples:
#   ./rds-pull-dump.sh --ssh ubuntu@3.11.2.1 --remote-dir /srv/pattika
#   ./rds-pull-dump.sh --ssh ubuntu@3.11.2.1 --remote-dir /srv/pattika ~/dumps
#
# Flags (must come before the positional backup-dir):
#   --ssh          SSH target of the EC2 host (or env RDS_PULL_SSH)
#   --remote-dir   server project dir holding the server .env
#                  (or env RDS_PULL_REMOTE_DIR)
#   --no-check     skip the local pg_restore --list sanity check
#   --verify       also restore into a local scratch DB, count tables, drop it
set -euo pipefail
cd "$(dirname "$0")"

SSH_TARGET="${RDS_PULL_SSH:-}"
REMOTE_DIR="${RDS_PULL_REMOTE_DIR:-}"
NO_CHECK=0
VERIFY=0

usage() {
    sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h) usage 0 ;;
        --ssh) SSH_TARGET="${2:?--ssh needs value}"; shift 2 ;;
        --remote-dir) REMOTE_DIR="${2:?--remote-dir needs value}"; shift 2 ;;
        --no-check) NO_CHECK=1; shift ;;
        --verify) VERIFY=1; shift ;;
        --*) echo "Unknown flag: $1 (see --help)" >&2; exit 2 ;;
        *) break ;;
    esac
done
BACKUP_DIR="${1:-$HOME/backups/pattika}"

if [[ -z "$SSH_TARGET" ]]; then
    echo "Missing --ssh user@host (or RDS_PULL_SSH env)" >&2
    exit 2
fi
if [[ -z "$REMOTE_DIR" ]]; then
    echo "Missing --remote-dir /path/to/server/project (or RDS_PULL_REMOTE_DIR env)" >&2
    exit 2
fi

if [[ ! -f .env ]]; then
    echo "Local .env not found (needed for --verify local DB creds)" >&2
    exit 2
fi

# shellcheck disable=SC1090
# NOTE: parsed, never sourced (values may contain shell metacharacters).
load_env_file() {
    local file="$1" line key value
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        [[ "$line" =~ ^[[:space:]]*$ ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" =~ ^[[:space:]]*export[[:space:]]+ ]] && \
            line="${line#*export}" && line="${line#"${line%%[![:space:]]*}"}"
        if [[ ! "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            continue
        fi
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
    if [[ -z "${!var:-}" ]]; then
        echo "Required local variable $var missing from .env (--verify)" >&2
        exit 2
    fi
done

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
DUMP_FILE="$BACKUP_DIR/pattika_rds_${STAMP}.dump"
LOG_FILE="$BACKUP_DIR/pull_${STAMP}.log"

log() {
    echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE" >&2
}
die() {
    log "FATAL: $*"
    exit 1
}

log "Pulling fresh dump: $SSH_TARGET:$REMOTE_DIR -> $DUMP_FILE"
mkdir -p "$(dirname "$LOG_FILE")"

# The remote half runs in its own bash so the server .env is parsed there
# with the same never-source rules. ALL diagnostics go to stderr; stdout
# is reserved for the dump bytes streaming back over SSH.
REMOTE_SCRIPT=$(cat <<'REMOTE_EOF'
set -euo pipefail
cd "$1"

if [[ ! -f .env ]]; then
    echo "[remote] .env not found in $(pwd)" >&2
    exit 2
fi

while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^[[:space:]]*export[[:space:]]+ ]] && \
        line="${line#*export}" && line="${line#"${line%%[![:space:]]*}"}"
    if [[ ! "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
        continue
    fi
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    if [[ "${value:0:1}" == "'" && "${value: -1}" == "'" && ${#value} -ge 2 ]]; then
        value="${value:1:-1}"
    fi
    printf -v "$key" '%s' "$value"
    export "$key"
done < .env

for var in DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME; do
    [[ -n "${!var:-}" ]] || { echo "[remote] $var missing from .env" >&2; exit 2; }
done

export PGPASSWORD="$DB_PASSWORD"
PSQL="psql -h $DB_HOST -p $DB_PORT -U $DB_USER -w -tA"

pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null \
    || { echo "[remote] RDS not reachable" >&2; exit 2; }
PG_MAJOR=$("$PSQL" -d postgres -c "SHOW server_version_num;" | cut -c1-2)
echo "[remote] server major: $PG_MAJOR, dumping $DB_NAME" >&2

if command -v pg_dump >/dev/null 2>&1 && \
   [[ "$(pg_dump --version | grep -oE '[0-9]+' | head -n1)" -ge "$PG_MAJOR" ]]; then
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -w -Fc "$DB_NAME"
else
    command -v docker >/dev/null 2>&1 \
        || { echo "[remote] no version-matched pg_dump and no docker" >&2; exit 2; }
    echo "[remote] using throwaway postgres:${PG_MAJOR}-alpine for version-matched dump" >&2
    docker pull -q "postgres:${PG_MAJOR}-alpine" >&2
    docker run --rm -e PGPASSWORD="$DB_PASSWORD" "postgres:${PG_MAJOR}-alpine" \
        pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -w -Fc "$DB_NAME"
fi
REMOTE_EOF
)
if ! ssh "$SSH_TARGET" bash -s -- "$REMOTE_DIR" <<< "$REMOTE_SCRIPT" > "$DUMP_FILE.part" 2> >(tee -a "$LOG_FILE" >&2); then
    rm -f "$DUMP_FILE.part"
    die "SSH dump failed"
fi

[[ -s "$DUMP_FILE.part" ]] || { rm -f "$DUMP_FILE.part"; die "Dump is empty"; }
mv "$DUMP_FILE.part" "$DUMP_FILE"
log "Dump received: $(du -h "$DUMP_FILE" | cut -f1)"

if [[ "$NO_CHECK" -eq 0 ]]; then
    pg_restore --list "$DUMP_FILE" >/dev/null 2>&1 \
        || die "Dump failed pg_restore --list"
    log "pg_restore --list OK"
fi

if [[ "$VERIFY" -eq 1 ]]; then
    SCRATCH="pattika_pull_check_${STAMP}"
    LOCAL_PSQL="psql -h $DB_HOST -p $DB_PORT -U $DB_USER -w -v ON_ERROR_STOP=1 -tA"
    export PGPASSWORD="$DB_PASSWORD"
    log "Verifying restore into local scratch DB $SCRATCH"
    $LOCAL_PSQL -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH;"
    $LOCAL_PSQL -d postgres -c "CREATE DATABASE $SCRATCH OWNER \"$DB_USER\";"
    pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -w \
        --no-owner --no-privileges -j 4 -d "$SCRATCH" "$DUMP_FILE" \
        || { $LOCAL_PSQL -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH;" >/dev/null || true; die "Local restore failed"; }
    RESTORED=$($LOCAL_PSQL -d "$SCRATCH" -c \
        "SELECT count(*) FROM pg_tables WHERE schemaname NOT LIKE 'pg\_%' AND schemaname <> 'information_schema';")
    log "Restored tables locally: $RESTORED"
    $LOCAL_PSQL -d postgres -c "DROP DATABASE $SCRATCH;"
    log "Scratch dropped; verification passed"
fi

sha256sum "$DUMP_FILE" | tee -a "$BACKUP_DIR/SHA256SUMS" >&2

cat >&2 <<EOF
================================================================
DONE. Summary:
  dump:  $DUMP_FILE
  log:   $LOG_FILE

To use it locally:
  createdb -h localhost -p 5432 -U $DB_USER pattika_rds
  pg_restore -h localhost -p 5432 -U $DB_USER --no-owner --no-privileges -j 4 -d pattika_rds "$DUMP_FILE"
  # then set DB_NAME=pattika_rds in .env
================================================================
EOF
