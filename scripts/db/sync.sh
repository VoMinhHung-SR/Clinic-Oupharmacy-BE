#!/bin/bash
# Sync databases from local to container
# Usage: ./sync.sh [--force]

set -e

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

# Initialize
load_env
init_connection_settings

# Parse arguments
FORCE=false
if [[ "$1" == "--force" ]]; then
    FORCE=true
fi

# Source database (local)
LOCAL_USER="${DB_PG_USER}"
LOCAL_PASSWORD="${DB_PG_PASSWORD}"
LOCAL_DB_DEFAULT="${DB_PG_NAME_DEFAULT}"
LOCAL_DB_STORE="${DB_PG_NAME_STORE}"

# Target database (container)
CONTAINER_USER="${DB_PG_USER}"
CONTAINER_PASSWORD="${DB_PG_PASSWORD}"
CONTAINER_DB_DEFAULT="${DB_PG_NAME_DEFAULT}"
CONTAINER_DB_STORE="${DB_PG_NAME_STORE}"

echo "=========================================="
echo "Syncing database from local to container"
echo "=========================================="
echo "Source: ${LOCAL_USER}@${LOCAL_HOST}:${LOCAL_PORT}"
echo "Target: ${CONTAINER_USER}@${CONTAINER_HOST}:${CONTAINER_PORT}"
if [ "${FORCE}" = true ]; then
    log_warning "Force mode: Will drop existing data in target databases"
fi
echo ""

# Check local connection
if ! check_db_connection "${LOCAL_HOST}" "${LOCAL_PORT}" "${LOCAL_USER}" "${LOCAL_PASSWORD}"; then
    log_error "Cannot connect to local database at ${LOCAL_HOST}:${LOCAL_PORT}"
    log_info "Make sure local PostgreSQL is running"
    exit 1
fi

# Check container connection
if ! check_db_connection "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASSWORD}"; then
    log_error "Cannot connect to container database at ${CONTAINER_HOST}:${CONTAINER_PORT}"
    log_info "Make sure Docker containers are running: docker-compose up -d"
    exit 1
fi

# Function to sync database
sync_database() {
    local source_db=$1
    local target_db=$2
    local db_name=$3
    
    log_info "Syncing ${db_name}..."
    echo "  From: ${source_db}"
    echo "  To: ${target_db}"
    
    # Check if source database exists
    if ! database_exists "${LOCAL_HOST}" "${LOCAL_PORT}" "${LOCAL_USER}" "${LOCAL_PASSWORD}" "${source_db}"; then
        log_warning "Source database ${source_db} does not exist. Skipping..."
        return 0
    fi
    
    # Check if target database exists, create if not
    if ! database_exists "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASSWORD}" "${target_db}"; then
        log_info "Creating target database ${target_db}..."
        if ! PGPASSWORD="${CONTAINER_PASSWORD}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d postgres -c "CREATE DATABASE ${target_db};" >/dev/null 2>&1; then
            log_error "Failed to create target database ${target_db}"
            return 1
        fi
    fi
    
    # Dump from source and restore to target in one pipe
    log_info "Dumping and restoring data..."
    
    # Use temporary file for better error handling
    local temp_file=$(mktemp)
    local exit_code=0
    
    if PGPASSWORD="${LOCAL_PASSWORD}" pg_dump -h "${LOCAL_HOST}" -p "${LOCAL_PORT}" -U "${LOCAL_USER}" -d "${source_db}" \
        --clean --if-exists --no-owner --no-acl 2>"${temp_file}" | \
        PGPASSWORD="${CONTAINER_PASSWORD}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" \
        -d "${target_db}" -q >/dev/null 2>&1; then
        log_success "${db_name} synced successfully!"
    else
        # Check for critical errors
        if grep -q "FATAL\|ERROR" "${temp_file}" 2>/dev/null; then
            log_error "Failed to sync ${db_name}"
            cat "${temp_file}" >&2
            exit_code=1
        else
            log_warning "Some warnings occurred during sync, but operation completed"
        fi
    fi
    
    rm -f "${temp_file}"
    echo ""
    return ${exit_code}
}

# Sync databases
ERROR_COUNT=0
sync_database "${LOCAL_DB_DEFAULT}" "${CONTAINER_DB_DEFAULT}" "Default Database (${LOCAL_DB_DEFAULT})" || ((ERROR_COUNT++))
sync_database "${LOCAL_DB_STORE}" "${CONTAINER_DB_STORE}" "Store Database (${LOCAL_DB_STORE})" || ((ERROR_COUNT++))

echo "=========================================="
if [ ${ERROR_COUNT} -eq 0 ]; then
    log_success "Database sync completed!"
else
    log_error "Sync completed with ${ERROR_COUNT} error(s)"
fi
echo "=========================================="

exit ${ERROR_COUNT}

