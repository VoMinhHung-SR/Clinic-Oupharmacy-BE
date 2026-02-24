#!/bin/bash
# Backup databases từ container DB bằng Docker (không cần cài psql/pg_dump trên máy)
# Backup cả 2 DB: default và store
# Usage:
#   ./backup-docker.sh [backup_dir]           → 2 file: default_*.sql.gz, store_*.sql.gz
#   ./backup-docker.sh --all [backup_dir]      → 1 file: all_databases_*.sql.gz (pg_dumpall)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

load_env
init_connection_settings

# Parse --all
BACKUP_ALL=false
if [ "${1:-}" = "--all" ]; then
    BACKUP_ALL=true
    shift
fi

BACKUP_DIR="${1:-${DB_BACKUP_DIR:-${SCRIPT_DIR}/backups}}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "${BACKUP_DIR}"

# Tên container Postgres (trong docker-compose: container_name: postgres)
CONTAINER_NAME="${DB_CONTAINER_NAME:-postgres}"
CONTAINER_USER="${DB_PG_USER}"
CONTAINER_PASSWORD="${DB_PG_PASSWORD}"
CONTAINER_DB_DEFAULT="${DB_PG_NAME_DEFAULT}"
CONTAINER_DB_STORE="${DB_PG_NAME_STORE}"

echo "=========================================="
echo "Backup DB từ container (Docker)"
echo "=========================================="
echo "Container: ${CONTAINER_NAME}"
echo "Thư mục backup: ${BACKUP_DIR}"
echo ""

# Kiểm tra container đang chạy
if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    log_error "Container '${CONTAINER_NAME}' không chạy."
    log_info "Khởi động: docker-compose up -d (từ thư mục project)"
    exit 1
fi

# Chế độ 1 file (pg_dumpall): backup toàn bộ cluster
if [ "${BACKUP_ALL}" = true ]; then
    ALL_FILE="${BACKUP_DIR}/all_databases_${TIMESTAMP}.sql"
    ALL_GZ="${ALL_FILE}.gz"
    log_info "Backup toàn bộ (default + store) vào 1 file..."
    if docker exec -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
        pg_dumpall -U "${CONTAINER_USER}" --clean --if-exists --no-owner --no-acl \
        > "${ALL_FILE}" 2>/dev/null; then
        if command -v gzip >/dev/null 2>&1; then
            gzip -f "${ALL_FILE}"
            log_success "Lưu: ${ALL_GZ} ($(du -h "${ALL_GZ}" | cut -f1))"
        else
            log_success "Lưu: ${ALL_FILE} ($(du -h "${ALL_FILE}" | cut -f1))"
        fi
    else
        log_error "pg_dumpall thất bại."
        rm -f "${ALL_FILE}" "${ALL_GZ}"
        exit 1
    fi
    echo "=========================================="
    exit 0
fi

echo "Databases: ${CONTAINER_DB_DEFAULT}, ${CONTAINER_DB_STORE}"
echo ""

backup_one_db() {
    local db_name=$1
    local out_file="${BACKUP_DIR}/${db_name}_${TIMESTAMP}.sql"
    local out_gz="${out_file}.gz"

    log_info "Backing up ${db_name}..."
    # Full dump: schema + toàn bộ data (pg_dump mặc định đã gồm setval cho sequence)
    if docker exec -e PGPASSWORD="${CONTAINER_PASSWORD}" "${CONTAINER_NAME}" \
        pg_dump -U "${CONTAINER_USER}" -d "${db_name}" \
        --clean --if-exists --no-owner --no-acl -F p \
        > "${out_file}" 2>/dev/null; then
        if command -v gzip >/dev/null 2>&1; then
            gzip -f "${out_file}"
            log_success "${db_name} -> ${out_gz} ($(du -h "${out_gz}" | cut -f1))"
        else
            log_success "${db_name} -> ${out_file} ($(du -h "${out_file}" | cut -f1))"
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
