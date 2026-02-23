#!/bin/bash
# Restore DB từ file backup vào container (dùng Docker, không cần psql trên máy).
# Dùng cặp với backup-docker.sh: backup/restore đều chạy trong container.
# Usage: ./restore-docker.sh <backup_file> [database_name]
#   database_name mặc định đoán từ tên file (oupharmacydb / oupharmacy_store_db).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

load_env
init_connection_settings

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup_file> [database_name]"
    echo "  backup_file: file .sql hoặc .sql.gz (từ backup-docker.sh)"
    echo "  database_name: oupharmacydb | oupharmacy_store_db (mặc định đoán từ tên file)"
    echo "Example: $0 backups/oupharmacydb_20251204_225103.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"
TARGET_DB="${2:-}"

# Resolve path: nếu relative thì thử từ SCRIPT_DIR rồi từ thư mục backups
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

# Đoán target DB từ tên file nếu chưa chỉ định
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

CONTAINER_NAME="${DB_CONTAINER_NAME:-postgres}"
CONTAINER_USER="${DB_PG_USER}"
CONTAINER_PASSWORD="${DB_PG_PASSWORD}"

echo "=========================================="
echo "Restore DB vào container (Docker)"
echo "=========================================="
echo "File:   ${BACKUP_FILE}"
echo "Target: ${TARGET_DB} (container: ${CONTAINER_NAME})"
echo ""

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    log_error "Container '${CONTAINER_NAME}' không chạy. Chạy: docker-compose up -d"
    exit 1
fi

# Tạo DB nếu chưa có
exists=$(docker exec -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
    psql -U "${CONTAINER_USER}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '${TARGET_DB}';" 2>/dev/null || true)
if [ "${exists}" != "1" ]; then
    log_info "Tạo database ${TARGET_DB}..."
    docker exec -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${CONTAINER_USER}" -d postgres -c "CREATE DATABASE ${TARGET_DB};" >/dev/null 2>&1
fi

# Restore: pipe vào psql trong container
log_info "Đang restore..."
if [[ "${BACKUP_FILE}" == *.gz ]]; then
    if ! gunzip -c "${BACKUP_FILE}" | docker exec -i -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${CONTAINER_USER}" -d "${TARGET_DB}" -q 2>/dev/null; then
        log_error "Restore thất bại (có thể do lỗi trong file SQL)."
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

# Đồng bộ sequence (tránh lỗi duplicate key sau khi restore)
FIX_SEQ="${SCRIPT_DIR}/fix-sequences.sql"
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
