#!/bin/bash
# Backup databases from container
# Usage: ./backup.sh [backup_dir]

set -e

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"

# Initialize
load_env
init_connection_settings

# Backup directory (from env or argument or default)
BACKUP_DIR="${1:-${DB_BACKUP_DIR:-${SCRIPT_DIR}/backups}}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "${BACKUP_DIR}"

# Database connection (container)
CONTAINER_USER="${DB_PG_USER}"
CONTAINER_PASSWORD="${DB_PG_PASSWORD}"
CONTAINER_DB_DEFAULT="${DB_PG_NAME_DEFAULT}"
CONTAINER_DB_STORE="${DB_PG_NAME_STORE}"

echo "=========================================="
echo "Backing up databases from container"
echo "=========================================="
echo "Source: ${CONTAINER_USER}@${CONTAINER_HOST}:${CONTAINER_PORT}"
echo "Backup directory: ${BACKUP_DIR}"
echo ""

# Check container connection
if ! check_db_connection "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASSWORD}"; then
    log_error "Cannot connect to container database at ${CONTAINER_HOST}:${CONTAINER_PORT}"
    log_info "Make sure Docker containers are running: docker-compose up -d"
    exit 1
fi

# Function to backup database
backup_database() {
    local db_name=$1
    local backup_file="${BACKUP_DIR}/${db_name}_${TIMESTAMP}.sql"
    local backup_file_gz="${backup_file}.gz"
    
    log_info "Backing up ${db_name}..."
    echo "  To: ${backup_file}"
    
    # Check if database exists
    if ! database_exists "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${CONTAINER_USER}" "${CONTAINER_PASSWORD}" "${db_name}"; then
        log_warning "Database ${db_name} does not exist. Skipping..."
        return 0
    fi
    
    # Backup database
    if PGPASSWORD="${CONTAINER_PASSWORD}" pg_dump -h "${CONTAINER_HOST}" -p "${CONTAINER_PORT}" -U "${CONTAINER_USER}" -d "${db_name}" \
        --clean --if-exists --no-owner --no-acl -F p > "${backup_file}" 2>/dev/null; then
        
        # Compress backup
        if command -v gzip >/dev/null 2>&1; then
            gzip -f "${backup_file}"
            local file_size=$(du -h "${backup_file_gz}" | cut -f1)
            log_success "${db_name} backed up successfully! (Size: ${file_size}, compressed)"
        else
            local file_size=$(du -h "${backup_file}" | cut -f1)
            log_success "${db_name} backed up successfully! (Size: ${file_size})"
        fi
    else
        log_error "Failed to backup ${db_name}"
        rm -f "${backup_file}" "${backup_file_gz}"
        return 1
    fi
    echo ""
}

# Backup databases
ERROR_COUNT=0
backup_database "${CONTAINER_DB_DEFAULT}" || ((ERROR_COUNT++))
backup_database "${CONTAINER_DB_STORE}" || ((ERROR_COUNT++))

echo "=========================================="
if [ ${ERROR_COUNT} -eq 0 ]; then
    log_success "Backup completed!"
    echo "Backup files saved in: ${BACKUP_DIR}"
else
    log_error "Backup completed with ${ERROR_COUNT} error(s)"
fi
echo "=========================================="

exit ${ERROR_COUNT}

