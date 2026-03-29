#!/bin/bash
# Restore SQL backup into container. Host psql OR docker exec.
# Usage:
#   ./restore.sh <backup_file> [database_name]           — host psql → DB_CONTAINER_*
#   ./restore.sh --docker <backup_file> [database_name]  — pipe into psql inside container

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

USE_DOCKER=false
if [ "${1:-}" = "--docker" ]; then
  USE_DOCKER=true
  shift
fi

load_env
init_connection_settings

if [ $# -lt 1 ]; then
  echo "Usage: $0 [--docker] <backup_file> [database_name]" >&2
  exit 1
fi

BACKUP_FILE="$1"
TARGET_DB="${2:-}"

CONTAINER_USER="${DB_PG_USER}"
CONTAINER_PASSWORD="${DB_PG_PASSWORD}"
CONTAINER_NAME="${DB_CONTAINER_NAME:-postgres}"
FIX_SEQ="${SCRIPT_DIR}/fix-sequences.sql"

# ---------- Docker restore ----------
if [ "${USE_DOCKER}" = true ]; then
  if [ ! -f "${BACKUP_FILE}" ]; then
    [ -f "${SCRIPT_DIR}/${BACKUP_FILE}" ] && BACKUP_FILE="${SCRIPT_DIR}/${BACKUP_FILE}"
  fi
  BACKUP_DIR="${DB_BACKUP_DIR:-${SCRIPT_DIR}/backups}"
  if [ ! -f "${BACKUP_FILE}" ] && [ -f "${BACKUP_DIR}/$(basename "${BACKUP_FILE}")" ]; then
    BACKUP_FILE="${BACKUP_DIR}/$(basename "${BACKUP_FILE}")"
  fi
  if [ ! -f "${BACKUP_FILE}" ]; then
    log_error "File không tồn tại: ${BACKUP_FILE}"
    exit 1
  fi
  if [ -z "${TARGET_DB}" ]; then
    base=$(basename "${BACKUP_FILE}" | sed 's/\.gz$//')
    if [[ "${base}" == "${DB_PG_NAME_DEFAULT}"_* ]]; then
      TARGET_DB="${DB_PG_NAME_DEFAULT}"
    elif [[ "${base}" == "${DB_PG_NAME_STORE}"_* ]]; then
      TARGET_DB="${DB_PG_NAME_STORE}"
    else
      TARGET_DB="${DB_PG_NAME_DEFAULT}"
      log_info "Không đoán được DB từ tên file, dùng default: ${TARGET_DB}"
    fi
  fi
  echo "=========================================="
  echo "Restore DB vào container (Docker)"
  echo "=========================================="
  if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    log_error "Container '${CONTAINER_NAME}' không chạy."
    exit 1
  fi
  exists=$(docker exec -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
    psql -U "${CONTAINER_USER}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '${TARGET_DB}';" 2>/dev/null || true)
  if [ "${exists}" != "1" ]; then
    log_info "Tạo database ${TARGET_DB}..."
    docker exec -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
      psql -U "${CONTAINER_USER}" -d postgres -c "CREATE DATABASE ${TARGET_DB};" >/dev/null 2>&1
  fi
  log_info "Đang restore..."
  if [[ "${BACKUP_FILE}" == *.gz ]]; then
    if ! gunzip -c "${BACKUP_FILE}" | docker exec -i -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
      psql -U "${CONTAINER_USER}" -d "${TARGET_DB}" -q 2>/dev/null; then
      log_error "Restore thất bại."
      exit 1
    fi
  else
    if ! cat "${BACKUP_FILE}" | docker exec -i -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
      psql -U "${CONTAINER_USER}" -d "${TARGET_DB}" -q 2>/dev/null; then
      log_error "Restore thất bại."
      exit 1
    fi
  fi
  log_success "Restore xong: ${TARGET_DB}"
  if [ -f "${FIX_SEQ}" ]; then
    log_info "Đồng bộ sequence..."
    if cat "${FIX_SEQ}" | docker exec -i -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
      psql -U "${CONTAINER_USER}" -d "${TARGET_DB}" -q 2>/dev/null; then
      log_success "Sequence đã đồng bộ."
    else
      log_warning "fix-sequences có cảnh báo (có thể bỏ qua)."
    fi
  fi
  echo "=========================================="
  exit 0
fi

# ---------- Host psql restore ----------
TARGET_DB="${2:-${DB_PG_NAME_DEFAULT}}"

if [ ! -f "${BACKUP_FILE}" ]; then
  log_error "Backup file not found: ${BACKUP_FILE}"
  exit 1
fi

echo "=========================================="
echo "Restoring database from backup (host psql)"
echo "=========================================="
echo "Target: ${CONTAINER_USER}@${CONTAINER_HOST}:${CONTAINER_PORT}/${TARGET_DB}"
echo ""

if ! check_db_connection "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASSWORD}"; then
  log_error "Cannot connect to container database at ${CONTAINER_HOST}:${CONTAINER_PORT}"
  exit 1
fi

if ! database_exists "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASSWORD}" "${TARGET_DB}"; then
  log_info "Creating target database ${TARGET_DB}..."
  if ! PGPASSWORD="${CONTAINER_PASSWORD}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d postgres -c "CREATE DATABASE ${TARGET_DB};" >/dev/null 2>&1; then
    log_error "Failed to create target database ${TARGET_DB}"
    exit 1
  fi
fi

log_info "Restoring database..."
if [[ "${BACKUP_FILE}" == *.gz ]]; then
  if ! gunzip -c "${BACKUP_FILE}" | PGPASSWORD="${CONTAINER_PASSWORD}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d "${TARGET_DB}" >/dev/null 2>&1; then
    log_error "Failed to restore database"
    exit 1
  fi
else
  if ! PGPASSWORD="${CONTAINER_PASSWORD}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d "${TARGET_DB}" -f "${BACKUP_FILE}" >/dev/null 2>&1; then
    log_error "Failed to restore database"
    exit 1
  fi
fi
log_success "Database restored successfully!"

if [ -f "${FIX_SEQ}" ]; then
  log_info "Đồng bộ sequence..."
  if PGPASSWORD="${CONTAINER_PASSWORD}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d "${TARGET_DB}" -f "${FIX_SEQ}" -q >/dev/null 2>&1; then
    log_success "Sequence đã đồng bộ."
  else
    log_warning "Chạy fix-sequences có cảnh báo."
  fi
fi
echo "=========================================="
