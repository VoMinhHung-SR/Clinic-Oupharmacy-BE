#!/usr/bin/env bash
set -euo pipefail

# Load .env.production values (or export manually)
source ./scripts/db/config.sh
load_env
init_connection_settings

LOCAL_HOST="${DB_LOCAL_HOST:-127.0.0.1}"
LOCAL_PORT="${DB_LOCAL_PORT:-5432}"
LOCAL_USER="${DB_PG_USER:-postgres}"
LOCAL_DB="${DB_PG_NAME_DEFAULT:-oupharmacydb}"
LOCAL_PASS="${DB_PG_PASSWORD:-Hung123456}"

CONTAINER_HOST="${DB_CONTAINER_HOST:-localhost}"
CONTAINER_PORT="${DB_CONTAINER_PORT:-5433}"
CONTAINER_USER="${DB_PG_USER:-postgres}"
CONTAINER_DB="${DB_PG_NAME_DEFAULT:-oupharmacydb}"
CONTAINER_PASS="${DB_PG_PASSWORD:-Hung123456}"

echo "Local: ${LOCAL_USER}@${LOCAL_HOST}:${LOCAL_PORT}/${LOCAL_DB}"
echo "Target: ${CONTAINER_USER}@${CONTAINER_HOST}:${CONTAINER_PORT}/${CONTAINER_DB}"
echo

# Get list of public tables from local
TABLES=$(PGPASSWORD="${LOCAL_PASS}" psql -h "${LOCAL_HOST}" -p "${LOCAL_PORT}" -U "${LOCAL_USER}" -d "${LOCAL_DB}" -At -c "SELECT tablename FROM pg_tables WHERE schemaname='public';")

for t in ${TABLES}; do
  # Check if table exists on target
  exists=$(PGPASSWORD="${CONTAINER_PASS}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d "${CONTAINER_DB}" -At -c "SELECT to_regclass('public.\"${t}\"');")
  if [ -n "${exists}" ] && [ "${exists}" != "" ]; then
    echo "Syncing table: ${t}"
    # Dump only data for this table using column-inserts (safer) and pipe to target
    PGPASSWORD="${LOCAL_PASS}" pg_dump -h "${LOCAL_HOST}" -p "${LOCAL_PORT}" -U "${LOCAL_USER}" -d "${LOCAL_DB}" \
      --data-only --column-inserts --table="public.\"${t}\"" \
    | PGPASSWORD="${CONTAINER_PASS}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d "${CONTAINER_DB}"
    echo " -> Done ${t}"
  else
    echo "Skipping ${t} (not present in target)"
  fi
done

echo "Sync completed."