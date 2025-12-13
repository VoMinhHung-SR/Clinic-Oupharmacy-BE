#!/bin/bash
# Restore databases from backup file
# Usage: ./restore.sh <backup_file> [database_name]

set -e

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

# Initialize
load_env
init_connection_settings

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup_file> [database_name]"
    echo "Example: $0 backups/oupharmacydb_20251204_225103.sql.gz oupharmacydb"
    exit 1
fi

BACKUP_FILE="$1"
TARGET_DB="${2:-${DB_PG_NAME_DEFAULT}}"

# Check if backup file exists
if [ ! -f "${BACKUP_FILE}" ]; then
    log_error "Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

# Database connection (container)
CONTAINER_USER="${DB_PG_USER}"
CONTAINER_PASSWORD="${DB_PG_PASSWORD}"

echo "=========================================="
echo "Restoring database from backup"
echo "=========================================="
echo "Backup file: ${BACKUP_FILE}"
echo "Target: ${CONTAINER_USER}@${CONTAINER_HOST}:${CONTAINER_PORT}/${TARGET_DB}"
echo ""

# Check container connection
if ! check_db_connection "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASSWORD}"; then
    log_error "Cannot connect to container database at ${CONTAINER_HOST}:${CONTAINER_PORT}"
    log_info "Make sure Docker containers are running: docker-compose up -d"
    exit 1
fi

# Check if target database exists, create if not
if ! database_exists "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASSWORD}" "${TARGET_DB}"; then
    log_info "Creating target database ${TARGET_DB}..."
    if ! PGPASSWORD="${CONTAINER_PASSWORD}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d postgres -c "CREATE DATABASE ${TARGET_DB};" >/dev/null 2>&1; then
        log_error "Failed to create target database ${TARGET_DB}"
        exit 1
    fi
fi

# Restore database
log_info "Restoring database..."

if [[ "${BACKUP_FILE}" == *.gz ]]; then
    # Compressed backup
    if gunzip -c "${BACKUP_FILE}" | PGPASSWORD="${CONTAINER_PASSWORD}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d "${TARGET_DB}" >/dev/null 2>&1; then
        log_success "Database restored successfully!"
    else
        log_error "Failed to restore database"
        exit 1
    fi
else
    # Uncompressed backup
    if PGPASSWORD="${CONTAINER_PASSWORD}" psql -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d "${TARGET_DB}" -f "${BACKUP_FILE}" >/dev/null 2>&1; then
        log_success "Database restored successfully!"
    else
        log_error "Failed to restore database"
        exit 1
    fi
fi

echo "=========================================="

