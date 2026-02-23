#!/bin/bash
# Đồng bộ databases từ Container -> Local Instance
# Usage: ./sync-container-to-local.sh [--force]
#   --force: không hỏi, ghi đè dữ liệu local (dump dùng --clean --if-exists)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

load_env
init_connection_settings

FORCE=false
if [[ "${1:-}" == "--force" ]]; then
    FORCE=true
fi

# Source = Container
SOURCE_USER="${DB_PG_USER}"
SOURCE_PASSWORD="${DB_PG_PASSWORD}"
SOURCE_DB_DEFAULT="${DB_PG_NAME_DEFAULT}"
SOURCE_DB_STORE="${DB_PG_NAME_STORE}"
SOURCE_HOST="${CONTAINER_HOST}"
SOURCE_PORT="${CONTAINER_PORT}"

# Target = Local
TARGET_USER="${DB_PG_USER}"
TARGET_PASSWORD="${DB_PG_PASSWORD}"
TARGET_DB_DEFAULT="${DB_PG_NAME_DEFAULT}"
TARGET_DB_STORE="${DB_PG_NAME_STORE}"
TARGET_HOST="${LOCAL_HOST}"
TARGET_PORT="${LOCAL_PORT}"

echo "=========================================="
echo "Đồng bộ Container -> Local"
echo "=========================================="
echo "Nguồn (Container): ${SOURCE_USER}@${SOURCE_HOST}:${SOURCE_PORT}"
echo "Đích (Local):      ${TARGET_USER}@${TARGET_HOST}:${TARGET_PORT}"
if [ "${FORCE}" = true ]; then
    log_warning "Force: sẽ ghi đè dữ liệu hiện có trên Local"
fi
echo ""

# Kiểm tra kết nối Container
if ! check_db_connection "${SOURCE_HOST}" "${SOURCE_PORT}" "${SOURCE_USER}" "${SOURCE_PASSWORD}"; then
    log_error "Không kết nối được tới Container tại ${SOURCE_HOST}:${SOURCE_PORT}"
    log_info "Chạy: docker-compose up -d"
    exit 1
fi

# Kiểm tra kết nối Local
if ! check_db_connection "${TARGET_HOST}" "${TARGET_PORT}" "${TARGET_USER}" "${TARGET_PASSWORD}"; then
    log_error "Không kết nối được tới Local PostgreSQL tại ${TARGET_HOST}:${TARGET_PORT}"
    log_info "Đảm bảo PostgreSQL đang chạy trên máy (vd: sudo systemctl start postgresql)"
    exit 1
fi

sync_one_db() {
    local source_db=$1
    local target_db=$2
    local label=$3
    local temp_file
    temp_file=$(mktemp)
    local exit_code=0

    log_info "Đồng bộ ${label}..."
    echo "  Từ (Container): ${source_db}"
    echo "  Đến (Local):    ${target_db}"

    if ! database_exists "${SOURCE_HOST}" "${SOURCE_PORT}" "${SOURCE_USER}" "${SOURCE_PASSWORD}" "${source_db}"; then
        log_warning "Database ${source_db} không tồn tại trên Container. Bỏ qua."
        rm -f "${temp_file}"
        return 0
    fi

    if ! database_exists "${TARGET_HOST}" "${TARGET_PORT}" "${TARGET_USER}" "${TARGET_PASSWORD}" "${target_db}"; then
        log_info "Tạo database ${target_db} trên Local..."
        if ! PGPASSWORD="${TARGET_PASSWORD}" psql -h "${TARGET_HOST}" -p "${TARGET_PORT}" -U "${TARGET_USER}" -d postgres -c "CREATE DATABASE ${target_db};" >/dev/null 2>&1; then
            log_error "Không tạo được database ${target_db}"
            rm -f "${temp_file}"
            return 1
        fi
    fi

    log_info "Dump từ Container và restore vào Local (full records)..."
    if PGPASSWORD="${SOURCE_PASSWORD}" pg_dump -h "${SOURCE_HOST}" -p "${SOURCE_PORT}" -U "${SOURCE_USER}" -d "${source_db}" \
        --clean --if-exists --no-owner --no-acl -F p 2>"${temp_file}" | \
        PGPASSWORD="${TARGET_PASSWORD}" psql -h "${TARGET_HOST}" -p "${TARGET_PORT}" -U "${TARGET_USER}" \
        -d "${target_db}" -q >/dev/null 2>&1; then
        log_success "${label} đồng bộ xong."
    else
        if grep -q "FATAL\|ERROR" "${temp_file}" 2>/dev/null; then
            log_error "Đồng bộ ${label} thất bại."
            cat "${temp_file}" >&2
            rm -f "${temp_file}"
            return 1
        else
            log_warning "Có cảnh báo khi đồng bộ nhưng đã chạy xong."
        fi
    fi
    rm -f "${temp_file}"

    # Fix sequence trên Local
    local fix_seq="${SCRIPT_DIR}/fix-sequences.sql"
    if [ -f "${fix_seq}" ]; then
        log_info "Đồng bộ sequence cho ${target_db} (Local)..."
        if PGPASSWORD="${TARGET_PASSWORD}" psql -h "${TARGET_HOST}" -p "${TARGET_PORT}" -U "${TARGET_USER}" -d "${target_db}" -f "${fix_seq}" -q >/dev/null 2>&1; then
            log_success "Sequence đã đồng bộ."
        fi
    fi
    echo ""
    return ${exit_code}
}

ERROR_COUNT=0
sync_one_db "${SOURCE_DB_DEFAULT}" "${TARGET_DB_DEFAULT}" "Default (${SOURCE_DB_DEFAULT})" || ((ERROR_COUNT++))
sync_one_db "${SOURCE_DB_STORE}" "${TARGET_DB_STORE}" "Store (${SOURCE_DB_STORE})" || ((ERROR_COUNT++))

echo "=========================================="
if [ ${ERROR_COUNT} -eq 0 ]; then
    log_success "Đồng bộ Container -> Local hoàn tất."
else
    log_error "Hoàn tất với ${ERROR_COUNT} lỗi."
fi
echo "=========================================="

exit ${ERROR_COUNT}
