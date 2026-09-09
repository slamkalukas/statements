#!/usr/bin/env bash
# A throwaway Statements stack for trying things out — its own empty database,
# its own ports, a known login. Nothing here touches the real stack or its data.
#
#   ./scripts/scratch-stack.sh up      # start it   (API on :8099)
#   ./scripts/scratch-stack.sh down    # remove it, database and all
#
# The backend runs the image but with backend/app bind-mounted, so it serves the
# code in your working tree. Tables are created from the current models on boot
# (ENV=development), so no migration step is needed for a fresh database.
#
# Log in with:  admin@example.com / testpass123
#
# For the UI, the "statements-scratch" entry in ../../.claude/launch.json runs a
# Vite dev server on :5175 proxying to this API.
set -euo pipefail

NET=pdtest-net
DB=pdtest-db
API=pdtest-api
IMAGE=${BACKEND_IMAGE:-slamkalukas/statements-backend:latest}

# Docker Desktop needs a Windows-style path here. Handing it a Git Bash POSIX
# path (/c/Users/...) silently mounts a stale snapshot instead of the live
# folder, so the container quietly serves old code — `pwd -W` avoids that.
_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  if pwd -W >/dev/null 2>&1; then pwd -W; else pwd; fi
}
APP_DIR="$(_root)/backend/app"

case "${1:-}" in
  up)
    docker network create "$NET" >/dev/null 2>&1 || true
    docker run -d --name "$DB" --network "$NET" \
      -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test \
      postgres:16-alpine >/dev/null
    until docker exec "$DB" pg_isready -U test >/dev/null 2>&1; do sleep 1; done
    docker run -d --name "$API" --network "$NET" \
      -e DATABASE_URL=postgresql+psycopg2://test:test@"$DB":5432/test \
      -e ENV=development \
      -e ADMIN_EMAIL=admin@example.com -e ADMIN_PASSWORD=testpass123 \
      -v "$APP_DIR:/app/app" \
      -p 8099:8000 "$IMAGE" >/dev/null
    echo "scratch API on http://localhost:8099  (admin@example.com / testpass123)"
    ;;
  down)
    docker rm -f "$API" "$DB" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
    echo "scratch stack removed"
    ;;
  *)
    echo "usage: $0 {up|down}" >&2
    exit 1
    ;;
esac
