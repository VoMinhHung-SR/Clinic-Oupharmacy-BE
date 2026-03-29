#!/bin/bash
# Backup container DBs. Host pg_dump OR docker exec (no local psql needed).
# Usage:
#   ./backup.sh [backup_dir]                    — pg_dump from host to container port
#   ./backup.sh --docker [backup_dir]         — 2 files via docker exec
#   ./backup.sh --docker --all [backup_dir]   — one pg_dumpall file

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

USE_DOCKER=false
BACKUP_ALL=false
while [ $# -gt 0 ]; do
  case "$1" in
    --docker) USE_DOCKER=true; shift ;;
    --all)    BACKUP_ALL=true; shift ;;
    *)        break ;;
  esac
done

load_env
init_connection_settings

BACKUP_DIR="${1:-${DB_BACKUP_DIR:-${SCRIPT_DIR}/backups}}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "${BACKUP_DIR}"

CONTAINER_USER="${DB_PG_USER}"
CONTAINER_PASSWORD="${DB_PG_PASSWORD}"
CONTAINER_DB_DEFAULT="${DB_PG_NAME_DEFAULT}"
CONTAINER_DB_STORE="${DB_PG_NAME_STORE}"
CONTAINER_NAME="${DB_CONTAINER_NAME:-postgres}"

# ---------- Docker: pg_dumpall ----------
if [ "${USE_DOCKER}" = true ] && [ "${BACKUP_ALL}" = true ]; then
  echo "=========================================="
  echo "Backup DB từ container (Docker) — pg_dumpall"
  echo "=========================================="
  if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    log_error "Container '${CONTAINER_NAME}' không chạy."
    exit 1
  fi
  ALL_FILE="${BACKUP_DIR}/all_databases_${TIMESTAMP}.sql"
  ALL_GZ="${ALL_FILE}.gz"
  log_info "Backup toàn bộ cluster vào 1 file..."
  if docker exec -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
      pg_dumpall -U "${CONTAINER_USER}" --clean --if-exists --no-owner --no-acl \
      > "${ALL_FILE}" 2>/dev/null; then
    if command -v gzip >/dev/null 2>&1; then
      gzip -f "${ALL_FILE}"
      log_success "Lưu: ${ALL_GZ} ($(du -h "${ALL_GZ}" | cut -f1))"
    else
      log_success "Lưu: ${ALL_FILE}"
    fi
  else
    log_error "pg_dumpall thất bại."
    rm -f "${ALL_FILE}" "${ALL_GZ}"
    exit 1
  fi
  echo "=========================================="
  exit 0
fi

# ---------- Docker: 2x pg_dump ----------
if [ "${USE_DOCKER}" = true ]; then
  echo "=========================================="
  echo "Backup DB từ container (Docker)"
  echo "=========================================="
  echo "Container: ${CONTAINER_NAME}"
  echo "Thư mục backup: ${BACKUP_DIR}"
  echo ""
  if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    log_error "Container '${CONTAINER_NAME}' không chạy."
    exit 1
  fi
  backup_one_db() {
    local db_name=$1
    local out_file="${BACKUP_DIR}/${db_name}_${TIMESTAMP}.sql"
    local out_gz="${out_file}.gz"
    log_info "Backing up ${db_name}..."
    if docker exec -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
        pg_dump -U "${CONTAINER_USER}" -d "${db_name}" \
        --clean --if-exists --no-owner --no-acl -F p \
        > "${out_file}" 2>/dev/null; then
      if command -v gzip >/dev/null 2>&1; then
        gzip -f "${out_file}"
        log_success "${db_name} -> ${out_gz} ($(du -h "${out_gz}" | cut -f1))"
      else
        log_success "${db_name} -> ${out_file}"
      fi
    else
      log_warning "Database ${db_name} không tồn tại hoặc lỗi, bỏ qua."
      rm -f "${out_file}" "${out_gz}"
      return 1
    fi
    echo ""
    return 0
  }
  ERROR_COUNT=0
  backup_one_db "${CONTAINER_DB_DEFAULT}" || ((ERROR_COUNT++))
  backup_one_db "${CONTAINER_DB_STORE}" || ((ERROR_COUNT++))
  echo "=========================================="
  if [ ${ERROR_COUNT} -eq 0 ]; then
    log_success "Backup xong. File lưu tại: ${BACKUP_DIR}"
  else
    log_error "Backup kết thúc với ${ERROR_COUNT} lỗi."
  fi
  echo "=========================================="
  exit ${ERROR_COUNT}
fi

# ---------- Host: pg_dump ----------
echo "=========================================="
echo "Backing up databases from container (host pg_dump)"
echo "=========================================="
echo "Source: ${CONTAINER_USER}@${CONTAINER_HOST}:${CONTAINER_PORT}"
echo "Backup directory: ${BACKUP_DIR}"
echo ""

if ! check_db_connection "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASSWORD}"; then
  log_error "Cannot connect to container database at ${CONTAINER_HOST}:${CONTAINER_PORT}"
  exit 1
fi

backup_database() {
  local db_name=$1
  local backup_file="${BACKUP_DIR}/${db_name}_${TIMESTAMP}.sql"
  local backup_file_gz="${backup_file}.gz"
  log_info "Backing up ${db_name}..."
  if ! database_exists "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASSWORD}" "${db_name}"; then
    log_warning "Database ${db_name} does not exist. Skipping..."
    return 0
  fi
  if PGPASSWORD="${CONTAINER_PASSWORD}" pg_dump -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d "${db_name}" \
      --clean --if-exists --no-owner --no-acl -F p > "${backup_file}" 2>/dev/null; then
    if command -v gzip >/dev/null 2>&1; then
      gzip -f "${backup_file}"
      log_success "${db_name} backed up! ($(du -h "${backup_file_gz}" | cut -f1))"
    else
      log_success "${db_name} backed up!"
    fi
  else
    log_error "Failed to backup ${db_name}"
    rm -f "${backup_file}" "${backup_file_gz}"
    return 1
  fi
  echo ""
}

ERROR_COUNT=0
backup_database "${CONTAINER_DB_DEFAULT}" || ((ERROR_COUNT++))
backup_database "${CONTAINER_DB_STORE}" || ((ERROR_COUNT++))

echo "=========================================="
if [ ${ERROR_COUNT} -eq 0 ]; then
  log_success "Backup completed! Files in: ${BACKUP_DIR}"
else
  log_error "Backup completed with ${ERROR_COUNT} error(s)"
fi
echo "=========================================="
exit ${ERROR_COUNT}
