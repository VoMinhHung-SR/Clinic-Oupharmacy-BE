#!/usr/bin/env bash
# Database Sync with Drop: Clear container and sync from local
# Purpose: Drop all tables in container database, then sync from localhost:5432 -> container:5433
# Ready for step 5: Django migrations
# Usage: ./sync_and_drop.sh

set -euo pipefail

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

load_env
init_connection_settings

# Configuration variables
LOCAL_HOST="${DB_LOCAL_HOST:-127.0.0.1}"
LOCAL_PORT="${DB_LOCAL_PORT:-5432}"
LOCAL_USER="${DB_PG_USER:-postgres}"
LOCAL_PASS="${DB_PG_PASSWORD:-Hung123456}"
LOCAL_DB_DEFAULT="${DB_PG_NAME_DEFAULT:-oupharmacydb}"
LOCAL_DB_STORE="${DB_PG_NAME_STORE:-oupharmacy_store_db}"

CONTAINER_HOST="${DB_CONTAINER_HOST:-localhost}"
CONTAINER_PORT="${DB_CONTAINER_PORT:-5433}"
CONTAINER_USER="${DB_PG_USER:-postgres}"
CONTAINER_PASS="${DB_PG_PASSWORD:-Hung123456}"
CONTAINER_DB_DEFAULT="${DB_PG_NAME_DEFAULT:-oupharmacydb}"
CONTAINER_DB_STORE="${DB_PG_NAME_STORE:-oupharmacy_store_db}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✅${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠️${NC} $1"
}

log_error() {
    echo -e "${RED}❌${NC} $1"
}

# Print header
print_header() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  DB SYNC: Drop Tables + Sync from Local to Container ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Check if database exists
database_exists() {
    local host=$1
    local port=$2
    local user=$3
    local password=$4
    local db_name=$5
    
    PGPASSWORD="${password}" psql -h "${host}" -p "${port}" -U "${user}" -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "${db_name}"
}

# Step 1: Check database connections
step_check_connections() {
    echo -e "${YELLOW}Step 1: Checking database connections...${NC}"
    
    # Check local connection
    if ! PGPASSWORD="${LOCAL_PASS}" psql -h "${LOCAL_HOST}" -p "${LOCAL_PORT}" -U "${LOCAL_USER}" -d postgres -c "SELECT 1;" >/dev/null 2>&1; then
        log_error "Cannot connect to local database at ${LOCAL_HOST}:${LOCAL_PORT}"
        exit 1
    fi
    log_success "Local DB (${LOCAL_HOST}:${LOCAL_PORT}) is accessible"
    
    # Check container connection
    if ! PGPASSWORD="${CONTAINER_PASS}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d postgres -c "SELECT 1;" >/dev/null 2>&1; then
        log_error "Cannot connect to container database at ${CONTAINER_HOST}:${CONTAINER_PORT}"
        exit 1
    fi
    log_success "Container DB (${CONTAINER_HOST}:${CONTAINER_PORT}) is accessible"
    echo ""
}

# Step 2: Drop all tables in container databases
step_drop_tables() {
    echo -e "${YELLOW}Step 2: Dropping all tables in container databases...${NC}"
    
    drop_all_tables_in_db() {
        local host=$1
        local port=$2
        local user=$3
        local password=$4
        local db_name=$5
        local db_display_name=$6
        
        # Check if database exists
        if ! database_exists "${host}" "${port}" "${user}" "${password}" "${db_name}"; then
            log_warning "Database ${db_display_name} does not exist in container. Creating..."
            if PGPASSWORD="${password}" psql -h "${host}" -p "${port}" -U "${user}" -d postgres -c "CREATE DATABASE ${db_name};" >/dev/null 2>&1; then
                log_success "Database ${db_display_name} created"
            else
                log_error "Failed to create database ${db_display_name}"
                return 1
            fi
            return 0
        fi
        
        log_info "Dropping all tables from ${db_display_name}..."
        
        # SQL to drop all tables, views, sequences, functions
        local drop_sql="
        DROP SCHEMA public CASCADE;
        CREATE SCHEMA public;
        GRANT ALL ON SCHEMA public TO ${user};
        GRANT ALL ON SCHEMA public TO public;
        "
        
        if PGPASSWORD="${password}" psql -h "${host}" -p "${port}" -U "${user}" -d "${db_name}" -c "${drop_sql}" >/dev/null 2>&1; then
            log_success "All tables dropped from ${db_display_name}"
            return 0
        else
            log_error "Failed to drop tables from ${db_display_name}"
            return 1
        fi
    }
    
    # Drop tables from both container databases (continue even if one fails)
    drop_all_tables_in_db "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASS}" \
        "${CONTAINER_DB_DEFAULT}" "${CONTAINER_DB_DEFAULT}" || log_warning "Skipping ${CONTAINER_DB_DEFAULT}"
    
    drop_all_tables_in_db "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASS}" \
        "${CONTAINER_DB_STORE}" "${CONTAINER_DB_STORE}" || log_warning "Skipping ${CONTAINER_DB_STORE}"
    
    echo ""
}

# Step 3: Sync data from local to container
step_sync_data() {
    echo -e "${YELLOW}Step 3: Syncing data from local to container...${NC}"
    
    sync_database() {
        local source_host=$1
        local source_port=$2
        local source_user=$3
        local source_pass=$4
        local source_db=$5
        
        local target_host=$6
        local target_port=$7
        local target_user=$8
        local target_pass=$9
        local target_db=${10}
        local db_display_name=${11}
        
        # Check if source database exists
        if ! database_exists "${source_host}" "${source_port}" "${source_user}" "${source_pass}" "${source_db}"; then
            log_warning "Source database ${source_db} does not exist. Skipping..."
            return 0
        fi
        
        log_info "Syncing ${db_display_name}..."
        echo "  From: ${source_user}@${source_host}:${source_port}/${source_db}"
        echo "  To:   ${target_user}@${target_host}:${target_port}/${target_db}"
        
        # Check if target database exists, create if not
        if ! database_exists "${target_host}" "${target_port}" "${target_user}" "${target_pass}" "${target_db}"; then
            log_info "Creating target database ${target_db}..."
            if ! PGPASSWORD="${target_pass}" psql -h "${target_host}" -p "${target_port}" -U "${target_user}" -d postgres -c "CREATE DATABASE ${target_db};" >/dev/null 2>&1; then
                log_error "Failed to create target database ${target_db}"
                return 1
            fi
        fi
        
        # Dump from source and restore to target in one pipe
        local temp_file=$(mktemp)
        local exit_code=0
        
        if PGPASSWORD="${source_pass}" pg_dump -h "${source_host}" -p "${source_port}" -U "${source_user}" -d "${source_db}" \
            --clean --if-exists --no-owner --no-acl 2>"${temp_file}" | \
            PGPASSWORD="${target_pass}" psql -h "${target_host}" -p "${target_port}" -U "${target_user}" \
            -d "${target_db}" -q >/dev/null 2>&1; then
            log_success "${db_display_name} synced successfully!"
        else
            # Check for critical errors
            if grep -q "FATAL\|ERROR" "${temp_file}" 2>/dev/null; then
                log_error "Failed to sync ${db_display_name}"
                cat "${temp_file}" >&2
                exit_code=1
            fi
        fi
        
        rm -f "${temp_file}"
        return ${exit_code}
    }
    
    # Sync both databases (continue even if one fails)
    sync_database "${LOCAL_HOST}" "${LOCAL_PORT}" "${LOCAL_USER}" "${LOCAL_PASS}" "${LOCAL_DB_DEFAULT}" \
        "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASS}" "${CONTAINER_DB_DEFAULT}" \
        "${LOCAL_DB_DEFAULT}" || log_warning "Failed to sync ${LOCAL_DB_DEFAULT}"
    
    sync_database "${LOCAL_HOST}" "${LOCAL_PORT}" "${LOCAL_USER}" "${LOCAL_PASS}" "${LOCAL_DB_STORE}" \
        "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASS}" "${CONTAINER_DB_STORE}" \
        "${LOCAL_DB_STORE}" || log_warning "Failed to sync ${LOCAL_DB_STORE}"
    
    echo ""
}

# Step 4: Verify sync
step_verify() {
    echo -e "${YELLOW}Step 4: Verifying sync...${NC}"
    
    verify_database() {
        local host=$1
        local port=$2
        local user=$3
        local password=$4
        local db_name=$5
        local db_display_name=$6
        
        if ! database_exists "${host}" "${port}" "${user}" "${password}" "${db_name}"; then
            echo "  ${db_display_name}: NOT FOUND"
            return 0
        fi
        
        local table_count=$(PGPASSWORD="${password}" psql -h "${host}" -p "${port}" -U "${user}" -d "${db_name}" \
            -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tail -1 | xargs)
        
        echo "  ${db_display_name}: ${table_count} tables"
    }
    
    echo "Container database schema:"
    verify_database "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASS}" \
        "${CONTAINER_DB_DEFAULT}" "└─ ${CONTAINER_DB_DEFAULT}"
    verify_database "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASS}" \
        "${CONTAINER_DB_STORE}" "└─ ${CONTAINER_DB_STORE}"
    
    echo ""
}

# Main execution
main() {
    print_header
    
    step_check_connections
    step_drop_tables
    step_sync_data
    step_verify
    
    echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║            ✅ Sync Complete! Ready for Step 5        ║${NC}"
    echo -e "${GREEN}║                                                    ║${NC}"
    echo -e "${GREEN}║    Next: Run Django migrations with:               ║${NC}"
    echo -e "${GREEN}║    docker exec postgres python manage.py migrate   ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
    echo ""
}

main