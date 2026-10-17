#!/usr/bin/env bash
# Deploy or update StyleSense on the homelab: pull, build, migrate, restart, check.
# Usage (from the repo root on the server):  ./scripts/deploy.sh [--no-pull]
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose --env-file .env -f infra/compose/compose.yml -f infra/compose/compose.prod.yml)

[ -f .env ] || { echo "No .env: copy .env.prod.example to .env and fill it in." >&2; exit 1; }
grep -q '^APP_ENV=production' .env || { echo ".env must have APP_ENV=production" >&2; exit 1; }
mkdir -p backups

if [ "${1:-}" != "--no-pull" ]; then
  echo "==> Pulling the latest main"
  git pull --ff-only
fi

VERSION="$(git rev-parse --short HEAD)"
export APP_VERSION="$VERSION"

if [ -n "$("${COMPOSE[@]}" ps -q postgres 2>/dev/null)" ]; then
  echo "==> Backing up the database before migrating"
  "${COMPOSE[@]}" run --rm --no-deps backup now || echo "(backup skipped)"
fi

echo "==> Building $VERSION"
"${COMPOSE[@]}" build --build-arg VERSION="$VERSION" migrate

echo "==> Migrating and starting"
"${COMPOSE[@]}" up -d --remove-orphans

echo "==> Waiting for the API"
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T api python -c \
    "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2).status == 200 else 1)" \
    2>/dev/null; then
    break
  fi
  sleep 2
done

echo "==> AI routes and prices (safe to re-run)"
./scripts/bootstrap-ai.sh

"${COMPOSE[@]}" ps
PUBLIC_URL="$(grep '^APP_PUBLIC_WEB_URL=' .env | cut -d= -f2-)"
echo
echo "Deployed $VERSION. Check: curl -s $PUBLIC_URL/readyz"
