#!/usr/bin/env bash
# Drop toàn bộ bảng trong container rồi đồng bộ Local -> Container (gọi sync.sh)
# Dùng khi muốn "ghi đè sạch" container bằng dữ liệu local.
# Usage: ./sync_and_drop.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

load_env
init_connection_settings

LOCAL_PASS="${DB_PG_PASSWORD}"
CONTAINER_PASS="${DB_PG_PASSWORD}"
CONTAINER_DB_DEFAULT="${DB_PG_NAME_DEFAULT}"
CONTAINER_DB_STORE="${DB_PG_NAME_STORE}"

print_header() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  DB SYNC: Drop Tables + Sync Local -> Container     ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Bước 1: Kiểm tra kết nối
step_check_connections() {
    echo -e "${YELLOW}Bước 1: Kiểm tra kết nối...${NC}"
    if ! check_db_connection "${LOCAL_HOST}" "${LOCAL_PORT}" "${DB_PG_USER}" "${DB_PG_PASSWORD}"; then
        log_error "Không kết nối được Local tại ${LOCAL_HOST}:${LOCAL_PORT}"
        exit 1
    fi
    log_success "Local (${LOCAL_HOST}:${LOCAL_PORT}) OK"
    if ! check_db_connection "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${DB_PG_USER}" "${DB_PG_PASSWORD}"; then
        log_error "Không kết nối được Container tại ${CONTAINER_HOST}:${CONTAINER_PORT}"
        exit 1
    fi
    log_success "Container (${CONTAINER_HOST}:${CONTAINER_PORT}) OK"
    echo ""
}

# Bước 2: Drop toàn bộ bảng trong 2 DB trên container
step_drop_tables() {
    echo -e "${YELLOW}Bước 2: Drop toàn bộ bảng trong container...${NC}"
    drop_schema_in_db() {
        local db_name=$1
        if ! database_exists "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${DB_PG_USER}" "${CONTAINER_PASS}" "${db_name}"; then
            log_warning "DB ${db_name} không tồn tại trên container. Đang tạo..."
            PGPASSWORD="${CONTAINER_PASS}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${DB_PG_USER}" -d postgres -c "CREATE DATABASE ${db_name};" >/dev/null 2>&1
            return 0
        fi
        log_info "Drop schema public trong ${db_name}..."
        local drop_sql="
        DROP SCHEMA public CASCADE;
        CREATE SCHEMA public;
        GRANT ALL ON SCHEMA public TO ${DB_PG_USER};
        GRANT ALL ON SCHEMA public TO public;
        "
        if PGPASSWORD="${CONTAINER_PASS}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${DB_PG_USER}" -d "${db_name}" -c "${drop_sql}" >/dev/null 2>&1; then
            log_success "Đã drop bảng trong ${db_name}"
        else
            log_error "Không drop được ${db_name}"
            return 1
        fi
    }
    drop_schema_in_db "${CONTAINER_DB_DEFAULT}" || true
    drop_schema_in_db "${CONTAINER_DB_STORE}" || true
    echo ""
}

# Bước 3: Đồng bộ (dùng chung sync.sh — đã gồm fix-sequences)
step_sync() {
    echo -e "${YELLOW}Bước 3: Đồng bộ Local -> Container (sync.sh)...${NC}"
    "${SCRIPT_DIR}/sync.sh"
}

# Bước 4: Verify
step_verify() {
    echo -e "${YELLOW}Bước 4: Kiểm tra...${NC}"
    for db_name in "${CONTAINER_DB_DEFAULT}" "${CONTAINER_DB_STORE}"; do
        if ! database_exists "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${DB_PG_USER}" "${CONTAINER_PASS}" "${db_name}"; then
            echo "  ${db_name}: không tồn tại"
            continue
        fi
        local count
        count=$(PGPASSWORD="${CONTAINER_PASS}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${DB_PG_USER}" -d "${db_name}" -At -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "0")
        echo "  ${db_name}: ${count} bảng"
    done
    echo ""
}

print_header
step_check_connections
step_drop_tables
step_sync
step_verify
echo -e "${GREEN}✅ Sync (drop + sync) hoàn tất.${NC}"
echo ""
