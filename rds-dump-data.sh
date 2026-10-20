#!/usr/bin/env bash
# Dump the current RDS database to a file, then optionally push it to your
# laptop over SSH.
#
# Two ways to run it:
#
# 1. Server mode (script lives on the server, run it there). This is
#    Phase 0 + Phase 1 of ./rds-fresh-db.sh, extracted: preflight read
#    checks, a version-matched pg_dump (throwaway Docker container of the
#    server's major, falling back to host binaries), and verification. It
#    creates nothing and never writes to the database. Use --copy-to when
#    the laptop is reachable FROM the server.
#
# 2. SSH mode (script lives on the laptop, run it here). It SSHes into the
#    server, parses the server .env there (credentials never leave the
#    server, never printed, never hardcoded), and pg_dump's fresh data
#    streaming the dump bytes back over the SSH connection. Use this when
#    the server can NOT reach the laptop. Verified locally afterwards.
#
# Usage:
#   Server mode:  ./rds-dump-data.sh [--copy-to [user@]host[:dest]] [backup-dir]
# SSH mode:     ./rds-dump-data.sh --ssh user@host [--ssh-key ~/.ssh/key.pem] --remote-dir /path [backup-dir]
#   ./rds-dump-data.sh --help
#
# Examples:
#   ./rds-dump-data.sh                                   (server: dump + verify)
#   ./rds-dump-data.sh /tmp/dumps                        (server: custom dir)
#   ./rds-dump-data.sh --copy-to me@10.0.0.7:/tmp/opencode
#   ./rds-dump-data.sh --ssh ubuntu@3.11.2.1 --remote-dir /srv/pattika   (laptop)
#   ./rds-dump-data.sh --ssh ec2-user@3.11.2.1 --ssh-key ~/.ssh/device.pem --remote-dir logkshana-hrm
#
# Flags (must come before the positional backup-dir):
#   --ssh user@host       SSH target of the server (SSH mode; or RDS_PULL_SSH env)
#   --ssh-key /path.pem   private key for the SSH connection (SSH mode)
#   --remote-dir /path    server project dir holding the server .env
#                         (SSH mode; or RDS_PULL_REMOTE_DIR env)
#   --copy-to [user@]host[:dest]
#                         server mode only: scp the verified dump to the
#                         laptop. dest defaults to /tmp/opencode/ when
#                         omitted and must end in / to keep the filename.
#   --yes                 skip nothing-prompt hooks (kept for parity)
#   --skip-restore-check  skip the restore-into-scratch verification step
#   --no-docker           server mode only: host pg_dump only, no container
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE="${ENV_FILE:-.env}"
SKIP_RESTORE_CHECK=0
NO_DOCKER=0
COPY_TO=""
SSH_TARGET=""
REMOTE_DIR=""
SSH_KEY=""

usage() {
    sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h) usage 0 ;;
        --yes) shift ;;                      # accepted, nothing to confirm
        --skip-restore-check) SKIP_RESTORE_CHECK=1; shift ;;
        --no-docker) NO_DOCKER=1; shift ;;
        --copy-to)
            COPY_TO="${2:?--copy-to needs [user@]host[:dest]}"
            shift 2
            ;;
        --ssh)
            SSH_TARGET="${2:?--ssh needs user@host}"
            shift 2
            ;;
        --ssh-key)
            SSH_KEY="${2:?--ssh-key needs path to the .pem}"
            shift 2
            ;;
        --remote-dir)
            REMOTE_DIR="${2:?--remote-dir needs /path/to/server/project}"
            shift 2
            ;;
        --*) echo "Unknown flag: $1 (see --help)" >&2; exit 2 ;;
        *) break ;;
    esac
done
BACKUP_DIR="${1:-$HOME/backups/pattika}"

if [[ -n "$COPY_TO" && "$COPY_TO" != *:* ]]; then
    COPY_TO="$COPY_TO:/tmp/opencode/"
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Env file not found: $ENV_FILE" >&2
    exit 2
fi

# shellcheck disable=SC1090
# NOTE: the env file is parsed, never sourced (same rules as rds-fresh-db.sh).
load_env_file() {
    local file="$1" line key value
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        [[ "$line" =~ ^[[:space:]]*$ ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" =~ ^[[:space:]]*export[[:space:]]+ ]] && \
            line="${line#*export}" && line="${line#"${line%%[![:space:]]*}"}"
        if [[ ! "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            echo "Warning: ignoring non-assignment line in $file: $line" >&2
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
load_env_file "$ENV_FILE"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$BACKUP_DIR/dump_${STAMP}.log"

log() {
    echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE" >&2
}
die() {
    log "FATAL: $*"
    exit 1
}

# ==================================================================
# SSH mode — run from the LAPTOP; the dump streams back over SSH.
# ==================================================================
if [[ -n "$SSH_TARGET" ]]; then
    if [[ -z "$REMOTE_DIR" ]]; then
        echo "--ssh mode also needs --remote-dir /path/to/server/project" >&2
        exit 2
    fi

    HOSTTAG="${SSH_TARGET#*@}"
    HOSTTAG="${HOSTTAG//[!a-zA-Z0-9._-]/-}"
    DUMP_FILE="$BACKUP_DIR/rds_${HOSTTAG}_${STAMP}.dump"

    # The remote half runs in its own bash so the server .env is parsed
    # there with the same never-source rules. ALL diagnostics go to
    # stderr; stdout is reserved for the dump bytes over SSH.
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
PG_MAJOR=$($PSQL -d postgres -c "SHOW server_version_num;" | cut -c1-2)
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

    log "Pulling fresh dump over SSH: $SSH_TARGET:$REMOTE_DIR -> $DUMP_FILE"
    for var in DB_HOST DB_PORT DB_USER DB_PASSWORD; do
        if [[ -z "${!var:-}" ]]; then
            log "Required local variable $var is missing from $ENV_FILE (--verify restore check)"
            exit 2
        fi
    done

    SSH_OPTS=()
    if [[ -n "$SSH_KEY" ]]; then
        [[ -f "$SSH_KEY" ]] || die "Key file not found: $SSH_KEY"
        SSH_OPTS=(-i "$SSH_KEY")
    fi

    if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" bash -s -- "$REMOTE_DIR" \
        <<< "$REMOTE_SCRIPT" > "$DUMP_FILE.part" 2> >(tee -a "$LOG_FILE" >&2)
    then
        rm -f "$DUMP_FILE.part"
        die "SSH dump failed"
    fi

    [[ -s "$DUMP_FILE.part" ]] || { rm -f "$DUMP_FILE.part"; die "Dump is empty"; }
    mv "$DUMP_FILE.part" "$DUMP_FILE"
    log "Dump received: $(du -h "$DUMP_FILE" | cut -f1)"

    if [[ "$SKIP_RESTORE_CHECK" -eq 1 ]]; then
        log "Restore verification SKIPPED (--skip-restore-check)"
    elif ! pg_restore --list "$DUMP_FILE" >/dev/null 2>&1; then
        die "Dump failed pg_restore --list"
    else
        SCRATCH="pattika_pull_check_${STAMP//[-]/_}"
        LOCAL_PSQL="psql -h $DB_HOST -p $DB_PORT -U $DB_USER -w -v ON_ERROR_STOP=1 -tA"
        export PGPASSWORD="$DB_PASSWORD"
        log "Verifying restore into local scratch DB $SCRATCH"
        $LOCAL_PSQL -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH;"
        $LOCAL_PSQL -d postgres -c "CREATE DATABASE $SCRATCH OWNER \"$DB_USER\";"
        pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -w \
            --no-owner --no-privileges -j 4 -d "$SCRATCH" "$DUMP_FILE" \
            || { $LOCAL_PSQL -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH;" >/dev/null 2>&1 || true;
                 die "Local restore into scratch failed"; }
        RESTORED_COUNT=$($LOCAL_PSQL -d "$SCRATCH" -c \
            "SELECT count(*) FROM pg_tables WHERE schemaname NOT LIKE 'pg\_%' AND schemaname <> 'information_schema';")
        [[ "$RESTORED_COUNT" -gt 0 ]] || die "Scratch DB has no tables after restore"
        $LOCAL_PSQL -d postgres -c "DROP DATABASE $SCRATCH;"
        log "Restore verification passed ($RESTORED_COUNT tables); scratch DB dropped"
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
    exit 0
fi

# ==================================================================
# Server mode — run ON the server; .env DB_* address the RDS itself.
# ==================================================================
for var in DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME; do
    if [[ -z "${!var:-}" ]]; then
        echo "Required variable $var is missing from $ENV_FILE" >&2
        exit 2
    fi
done

DUMP_FILE="$BACKUP_DIR/${DB_NAME}_${STAMP}.dump"

export PGPASSWORD="$DB_PASSWORD"
PSQL="psql -h $DB_HOST -p $DB_PORT -U $DB_USER -w -v ON_ERROR_STOP=1 -tA"

# ------------------------------------------------------------------
# Preflight — read-only.
# ------------------------------------------------------------------
log "Preflight against $DB_HOST:$DB_PORT (dumping $DB_NAME)"
pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null || die "Postgres not reachable"
PG_MAJOR=$($PSQL -d postgres -c "SHOW server_version_num;" | cut -c1-2)
log "Server major version: $PG_MAJOR"

# ------------------------------------------------------------------
# Version-matched dump tooling (same rules as rds-fresh-db.sh).
# ------------------------------------------------------------------
if [[ "$NO_DOCKER" -eq 0 ]] && command -v docker >/dev/null 2>&1; then
    PG_IMAGE="postgres:${PG_MAJOR}-alpine"
    log "Pulling $PG_IMAGE for version-matched pg_dump/pg_restore"
    docker pull "$PG_IMAGE" 2>&1 | tail -n 1 | tee -a "$LOG_FILE" >&2 \
        || die "Could not pull $PG_IMAGE (registry access required)"
    BACKUP_ABS="$(cd "$BACKUP_DIR" && pwd)"
    DUMP_IN_CONTAINER="/backups/$(basename "$DUMP_FILE")"
    DUMP_DB_HOST="$DB_HOST"
    DOCKER_GATEWAY_ARGS=()
    if [[ "$DB_HOST" == "localhost" || "$DB_HOST" == "127.0.0.1" ]]; then
        DUMP_DB_HOST="host.docker.internal"
        DOCKER_GATEWAY_ARGS=(--add-host=host.docker.internal:host-gateway)
    fi
    pg_dump_cmd() {
        docker run --rm "${DOCKER_GATEWAY_ARGS[@]}" -e "PGPASSWORD=$DB_PASSWORD" \
            -v "$BACKUP_ABS:/backups" "$PG_IMAGE" pg_dump -h "$DUMP_DB_HOST" "$@"
    }
    pg_restore_cmd() {
        docker run --rm "${DOCKER_GATEWAY_ARGS[@]}" -e "PGPASSWORD=$DB_PASSWORD" \
            -v "$BACKUP_ABS:/backups" "$PG_IMAGE" pg_restore -h "$DUMP_DB_HOST" "$@"
    }
else
    for tool in pg_dump pg_restore; do
        command -v "$tool" >/dev/null 2>&1 \
            || die "Missing $tool and no docker: install postgresql-client >= $PG_MAJOR or docker"
        tool_major=$($tool --version | grep -oE '[0-9]+' | head -n 1)
        [[ "$tool_major" -ge "$PG_MAJOR" ]] \
            || die "$tool $tool_major is too old for server $PG_MAJOR (needs >= $PG_MAJOR; retry without --no-docker)"
    done
    DUMP_IN_CONTAINER="$DUMP_FILE"
    pg_dump_cmd() { pg_dump -h "$DB_HOST" "$@"; }
    pg_restore_cmd() { pg_restore -h "$DB_HOST" "$@"; }
fi

# ------------------------------------------------------------------
# Dump (the database is only ever read).
# ------------------------------------------------------------------
log "Dumping $DB_NAME -> $DUMP_FILE"
pg_dump_cmd -p "$DB_PORT" -U "$DB_USER" -Fc -f "$DUMP_IN_CONTAINER" "$DB_NAME"
[[ -s "$DUMP_FILE" ]] || die "Dump file is empty"
pg_restore_cmd --list "$DUMP_IN_CONTAINER" >/dev/null || die "Dump file failed pg_restore --list"
sha256sum "$DUMP_FILE" | tee -a "$BACKUP_DIR/SHA256SUMS" >&2
log "Dump OK: $(du -h "$DUMP_FILE" | cut -f1)"

COPY_TARGET=""    # zero-filled in the copy step below, for the summary

if [[ "$SKIP_RESTORE_CHECK" -eq 0 ]]; then
    SCRATCH="${DB_NAME}_dump_check_${STAMP//[-]/_}"
    log "Restore verification into scratch DB $SCRATCH"
    $PSQL -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH;"
    $PSQL -d postgres -c "CREATE DATABASE $SCRATCH OWNER \"$DB_USER\";"
    pg_restore_cmd -p "$DB_PORT" -U "$DB_USER" -d "$SCRATCH" --no-owner "$DUMP_IN_CONTAINER" \
        || die "Restore into scratch DB failed"
    RESTORED_COUNT=$($PSQL -d "$SCRATCH" -c \
        "SELECT count(*) FROM pg_tables WHERE schemaname NOT LIKE 'pg\_%' AND schemaname <> 'information_schema';")
    [[ "$RESTORED_COUNT" -gt 0 ]] || die "Scratch DB has no tables after restore"
    $PSQL -d postgres -c "DROP DATABASE $SCRATCH;"
    log "Restore verification passed ($RESTORED_COUNT tables); scratch DB dropped"
else
    log "Restore verification SKIPPED (--skip-restore-check)"
fi

# ------------------------------------------------------------------
# Optional transfer — push the verified dump to another machine.
# ------------------------------------------------------------------
if [[ -n "$COPY_TO" ]]; then
    command -v scp >/dev/null 2>&1 || die "scp not found (needed for --copy-to)"
    log "Copying $DUMP_FILE -> $COPY_TO"
    scp "$DUMP_FILE" "$COPY_TO" >>"$LOG_FILE" 2>&1 || die "scp to $COPY_TO failed"
    log "Copy OK"
    COPY_TARGET="$COPY_TO"
fi

cat >&2 <<EOF
================================================================
DONE. Summary:
  dump:  $DUMP_FILE
  log:   $LOG_FILE
  sha:   computed (see SHA256SUMS)
  copy:  ${COPY_TARGET:-not requested (--copy-to)}

${COPY_TARGET:+Skip the local restore below and restore on the copying machine:}
  createdb -h localhost -p 5432 -U <local-user> pattika_rds
  pg_restore -h localhost -p 5432 -U <local-user> --no-owner --no-privileges -j 4 -d pattika_rds <dump>
  # then set DB_NAME=pattika_rds in your local .env
================================================================
EOF
