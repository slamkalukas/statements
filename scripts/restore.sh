#!/usr/bin/env bash
# Restore a database dump produced by backup.sh into the running db container.
# Usage: ./scripts/restore.sh backups/statements-<timestamp>.sql.gz
set -euo pipefail

cd "$(dirname "$0")/.."

if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup-file.sql.gz>" >&2
  exit 1
fi

dump="$1"
POSTGRES_USER="${POSTGRES_USER:-statements}"
POSTGRES_DB="${POSTGRES_DB:-statements}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

if [ ! -f "${dump}" ]; then
  echo "No such file: ${dump}" >&2
  exit 1
fi

echo "Restoring ${dump} into '${POSTGRES_DB}' (existing data will be overwritten)"
gunzip -c "${dump}" | docker compose -f "${COMPOSE_FILE}" exec -T db \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "Restore complete."
