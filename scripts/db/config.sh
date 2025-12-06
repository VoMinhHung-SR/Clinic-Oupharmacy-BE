#!/bin/bash
# Database configuration loader
# This file loads database configuration from .env.production

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Load environment variables from .env.production
load_env() {
    local env_file="${PROJECT_ROOT}/.env.production"
    
    if [ ! -f "${env_file}" ]; then
        echo "Error: .env.production not found at ${env_file}" >&2
        return 1
    fi
    
    # Load database credentials
    export DB_PG_USER=$(grep "^DB_PG_USER=" "${env_file}" | cut -d '=' -f2- | tr -d '"' | tr -d "'" | head -1)
    export DB_PG_PASSWORD=$(grep "^DB_PG_PASSWORD=" "${env_file}" | cut -d '=' -f2- | tr -d '"' | tr -d "'" | head -1)
    export DB_PG_NAME_DEFAULT=$(grep "^DB_PG_NAME_DEFAULT=" "${env_file}" | cut -d '=' -f2- | tr -d '"' | tr -d "'" | head -1)
    export DB_PG_NAME_STORE=$(grep "^DB_PG_NAME_STORE=" "${env_file}" | cut -d '=' -f2- | tr -d '"' | tr -d "'" | head -1)
    
    # Load local database connection settings
    export DB_LOCAL_HOST=$(grep "^DB_LOCAL_HOST=" "${env_file}" | cut -d '=' -f2- | tr -d '"' | tr -d "'" | head -1)
    export DB_LOCAL_PORT=$(grep "^DB_LOCAL_PORT=" "${env_file}" | cut -d '=' -f2- | tr -d '"' | tr -d "'" | head -1)
    
    # Load container database connection settings
    export DB_CONTAINER_HOST=$(grep "^DB_CONTAINER_HOST=" "${env_file}" | cut -d '=' -f2- | tr -d '"' | tr -d "'" | head -1)
    export DB_CONTAINER_PORT=$(grep "^DB_CONTAINER_PORT=" "${env_file}" | cut -d '=' -f2- | tr -d '"' | tr -d "'" | head -1)
    
    # Load backup directory setting
    export DB_BACKUP_DIR=$(grep "^DB_BACKUP_DIR=" "${env_file}" | cut -d '=' -f2- | tr -d '"' | tr -d "'" | head -1)
    
    # Set defaults if not found
    export DB_PG_USER="${DB_PG_USER:-postgres}"
    export DB_PG_PASSWORD="${DB_PG_PASSWORD:-Hung123456}"
    export DB_PG_NAME_DEFAULT="${DB_PG_NAME_DEFAULT:-oupharmacydb}"
    export DB_PG_NAME_STORE="${DB_PG_NAME_STORE:-oupharmacy_store_db}"
    export DB_LOCAL_HOST="${DB_LOCAL_HOST:-127.0.0.1}"
    export DB_LOCAL_PORT="${DB_LOCAL_PORT:-5432}"
    export DB_CONTAINER_HOST="${DB_CONTAINER_HOST:-localhost}"
    export DB_CONTAINER_PORT="${DB_CONTAINER_PORT:-5433}"
    export DB_BACKUP_DIR="${DB_BACKUP_DIR:-${SCRIPT_DIR}/backups}"
}

# Initialize connection settings after load_env is called
# These will be set dynamically when load_env() is called
LOCAL_HOST=""
LOCAL_PORT=""
CONTAINER_HOST=""
CONTAINER_PORT=""

# Function to initialize connection settings (call after load_env)
init_connection_settings() {
    LOCAL_HOST="${DB_LOCAL_HOST:-127.0.0.1}"
    LOCAL_PORT="${DB_LOCAL_PORT:-5432}"
    CONTAINER_HOST="${DB_CONTAINER_HOST:-localhost}"
    CONTAINER_PORT="${DB_CONTAINER_PORT:-5433}"
}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Check if database connection is available
check_db_connection() {
    local host=$1
    local port=$2
    local user=$3
    local password=$4
    local db_name=${5:-postgres}
    
    PGPASSWORD="${password}" psql -h "${host}" -p "${port}" -U "${user}" -d "${db_name}" -c "SELECT 1;" >/dev/null 2>&1
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

