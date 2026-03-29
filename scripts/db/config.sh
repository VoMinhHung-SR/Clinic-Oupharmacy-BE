#!/bin/bash
# Shared DB script config: one env load path for all scripts/db/*.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Parse KEY=VALUE without shell-evaluating values (no source), so &, $, #, * in secrets stay literal.
# Skips blank lines and # comments; optional leading "export "; strips one pair of outer ' or " on values.
_load_env_file() {
    local env_path="$1"
    local line key val q1 q2
    [[ -f "$env_path" ]] || return 0
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        [[ -z "${line// }" ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        if [[ "$line" =~ ^[[:space:]]*export[[:space:]]+(.*)$ ]]; then
            line="${BASH_REMATCH[1]}"
        fi
        case "$line" in
            *=*) ;;
            *) continue ;;
        esac
        key="${line%%=*}"
        val="${line#*=}"
        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        [[ -z "$key" ]] && continue
        [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
        if [[ ${#val} -ge 2 ]]; then
            q1="${val:0:1}"
            q2="${val: -1}"
            if [[ ( "$q1" == '"' && "$q2" == '"' ) || ( "$q1" == "'" && "$q2" == "'" ) ]]; then
                val="${val:1:-1}"
            fi
        fi
        export "${key}=${val}"
    done < "$env_path"
}

# Load .env.production then .env (later overrides), apply DB_* defaults.
load_env() {
    local loaded=0
    if [[ -f "${PROJECT_ROOT}/.env.production" ]]; then
        _load_env_file "${PROJECT_ROOT}/.env.production"
        loaded=1
    fi
    if [[ -f "${PROJECT_ROOT}/.env" ]]; then
        _load_env_file "${PROJECT_ROOT}/.env"
        loaded=1
    fi
    if [[ "${loaded}" -eq 0 ]]; then
        echo "Error: Need .env.production or .env in ${PROJECT_ROOT}" >&2
        return 1
    fi

    export DB_PG_USER="${DB_PG_USER:-postgres}"
    export DB_PG_PASSWORD="${DB_PG_PASSWORD:-Hung123456}"
    export DB_PG_NAME_DEFAULT="${DB_PG_NAME_DEFAULT:-oupharmacydb}"
    export DB_PG_NAME_STORE="${DB_PG_NAME_STORE:-oupharmacy_store_db}"
    export DB_LOCAL_HOST="${DB_LOCAL_HOST:-127.0.0.1}"
    export DB_LOCAL_PORT="${DB_LOCAL_PORT:-5432}"
    export DB_CONTAINER_HOST="${DB_CONTAINER_HOST:-localhost}"
    export DB_CONTAINER_PORT="${DB_CONTAINER_PORT:-5433}"
    export DB_BACKUP_DIR="${DB_BACKUP_DIR:-${SCRIPT_DIR}/backups}"
    export DB_CONTAINER_NAME="${DB_CONTAINER_NAME:-postgres}"
}

LOCAL_HOST=""
LOCAL_PORT=""
CONTAINER_HOST=""
CONTAINER_PORT=""

init_connection_settings() {
    LOCAL_HOST="${DB_LOCAL_HOST:-127.0.0.1}"
    LOCAL_PORT="${DB_LOCAL_PORT:-5432}"
    CONTAINER_HOST="${DB_CONTAINER_HOST:-localhost}"
    CONTAINER_PORT="${DB_CONTAINER_PORT:-5433}"
}

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

check_db_connection() {
    local host=$1
    local port=$2
    local user=$3
    local password=$4
    local db_name=${5:-postgres}

    PGPASSWORD="${password}" psql -h "${host}" -p "${port}" -U "${user}" -d "${db_name}" -c "SELECT 1;" >/dev/null 2>&1
}

database_exists() {
    local host=$1
    local port=$2
    local user=$3
    local password=$4
    local db_name=$5

    PGPASSWORD="${password}" psql -h "${host}" -p "${port}" -U "${user}" -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "${db_name}"
}
