#!/usr/bin/env bash
# Restore the database from a backup. DESTRUCTIVE: replaces all current data.
# Usage: ./scripts/restore.sh backups/stylesense-YYYYMMDD-HHMM.sql.gz
set -euo pipefail
cd "$(dirname "$0")/.."

FILE="${1:?usage: restore.sh backups/<file>.sql.gz}"
[ -f "$FILE" ] || { echo "No such file: $FILE" >&2; exit 1; }
COMPOSE=(docker compose --env-file .env -f infra/compose/compose.yml -f infra/compose/compose.prod.yml)
env_get() { grep "^$1=" .env | tail -1 | cut -d= -f2-; }
POSTGRES_USER="$(env_get POSTGRES_USER)"
POSTGRES_DB="$(env_get POSTGRES_DB)"

read -r -p "Replace ALL data in '$POSTGRES_DB' with $FILE? Type 'restore' to continue: " answer
[ "$answer" = "restore" ] || { echo "Cancelled."; exit 1; }

"${COMPOSE[@]}" stop api worker tunnel
"${COMPOSE[@]}" exec -T postgres psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE);" \
  -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"
gunzip -c "$FILE" | "${COMPOSE[@]}" exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q
"${COMPOSE[@]}" up -d
echo "Restored from $FILE."
