#!/usr/bin/env bash
# Đồng bộ chỉ DATA (data-only) cho các bảng đã tồn tại trên target.
# Chỉ DB default; chỉ những bảng có ở cả local và container. Không thay schema.
# Usage: chạy từ thư mục project: ./scripts/db/sync_existing_tables.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

load_env
init_connection_settings

# Dùng biến từ config (LOCAL_HOST, CONTAINER_HOST, ... đã có sau init_connection_settings)
LOCAL_USER="${DB_PG_USER}"
LOCAL_PASS="${DB_PG_PASSWORD}"
LOCAL_DB="${DB_PG_NAME_DEFAULT}"
CONTAINER_USER="${DB_PG_USER}"
CONTAINER_PASS="${DB_PG_PASSWORD}"
CONTAINER_DB="${DB_PG_NAME_DEFAULT}"

echo "Local:    ${LOCAL_USER}@${LOCAL_HOST}:${LOCAL_PORT}/${LOCAL_DB}"
echo "Target:   ${CONTAINER_USER}@${CONTAINER_HOST}:${CONTAINER_PORT}/${CONTAINER_DB}"
echo ""

TABLES=$(PGPASSWORD="${LOCAL_PASS}" psql -h "${LOCAL_HOST}" -p "${LOCAL_PORT}" -U "${LOCAL_USER}" -d "${LOCAL_DB}" -At -c "SELECT tablename FROM pg_tables WHERE schemaname='public';")

for t in ${TABLES}; do
  exists=$(PGPASSWORD="${CONTAINER_PASS}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d "${CONTAINER_DB}" -At -c "SELECT to_regclass('public.\"${t}\"');")
  if [ -n "${exists}" ] && [ "${exists}" != "" ]; then
    echo "Syncing table: ${t}"
    PGPASSWORD="${LOCAL_PASS}" pg_dump -h "${LOCAL_HOST}" -p "${LOCAL_PORT}" -U "${LOCAL_USER}" -d "${LOCAL_DB}" \
      --data-only --column-inserts --table="public.\"${t}\"" \
    | PGPASSWORD="${CONTAINER_PASS}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d "${CONTAINER_DB}" >/dev/null 2>&1
    echo " -> Done ${t}"
  else
    echo "Skipping ${t} (chưa có trên target)"
  fi
done

echo "Sync (existing tables, data-only) completed."
