#!/usr/bin/env bash
# Dump the Postgres database to a timestamped gzip file in ./backups.
#
# This backs up the METADATA only (periods, document index, audit log). The
# document files themselves live on your mapped DOCUMENTS_DIR_HOST folder — back
# that folder up with your normal file backups.
set -euo pipefail

cd "$(dirname "$0")/.."

POSTGRES_USER="${POSTGRES_USER:-statements}"
POSTGRES_DB="${POSTGRES_DB:-statements}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

mkdir -p backups
stamp="$(date +%Y%m%d-%H%M%S)"
out="backups/statements-${stamp}.sql.gz"

echo "Dumping database '${POSTGRES_DB}' -> ${out}"
docker compose -f "${COMPOSE_FILE}" exec -T db \
  pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "${out}"

echo "Done: ${out}"
