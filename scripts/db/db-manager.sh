#!/bin/bash
# Database Management Script
# Master script to manage all database operations
# Usage: ./db-manager.sh <command> [options]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

show_help() {
    echo -e "${BLUE}Database Management Script${NC}"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  backup              Backup databases from container"
    echo "  sync                Sync databases from local to container"
    echo "  restore <file>      Restore database from backup file"
    echo "  list-backups       List all backup files"
    echo "  status             Check database connection status"
    echo "  help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 backup"
    echo "  $0 sync"
    echo "  $0 sync --force"
    echo "  $0 restore backups/oupharmacydb_20251204_225103.sql.gz"
    echo "  $0 list-backups"
    echo "  $0 status"
}

COMMAND="${1:-help}"

case "${COMMAND}" in
    backup)
        "${SCRIPT_DIR}/backup.sh" "${@:2}"
        ;;
    sync)
        "${SCRIPT_DIR}/sync.sh" "${@:2}"
        ;;
    restore)
        if [ -z "$2" ]; then
            echo -e "${YELLOW}Error: Backup file required${NC}"
            echo "Usage: $0 restore <backup_file> [database_name]"
            exit 1
        fi
        "${SCRIPT_DIR}/restore.sh" "${@:2}"
        ;;
    list-backups)
        source "${SCRIPT_DIR}/config.sh"
        load_env
        BACKUP_DIR="${DB_BACKUP_DIR:-${SCRIPT_DIR}/backups}"
        if [ -d "${BACKUP_DIR}" ]; then
            echo -e "${BLUE}Backup files:${NC}"
            ls -lh "${BACKUP_DIR}"/*.sql* 2>/dev/null | awk '{print $9, "(" $5 ")"}' || echo "No backup files found"
        else
            echo "No backup directory found"
        fi
        ;;
    status)
        source "${SCRIPT_DIR}/config.sh"
        load_env
        init_connection_settings
        
        echo -e "${BLUE}Checking database connections...${NC}"
        echo ""
        
        # Check local
        if check_db_connection "${LOCAL_HOST}" "${LOCAL_PORT}" "${DB_PG_USER}" "${DB_PG_PASSWORD}"; then
            echo -e "${GREEN}✅${NC} Local database (${LOCAL_HOST}:${LOCAL_PORT}): Connected"
        else
            echo -e "${YELLOW}⚠️${NC} Local database (${LOCAL_HOST}:${LOCAL_PORT}): Not connected"
        fi
        
        # Check container
        if check_db_connection "${CONTAINER_HOST}" "${CONTAINER_PORT}" "${DB_PG_USER}" "${DB_PG_PASSWORD}"; then
            echo -e "${GREEN}✅${NC} Container database (${CONTAINER_HOST}:${CONTAINER_PORT}): Connected"
        else
            echo -e "${YELLOW}⚠️${NC} Container database (${CONTAINER_HOST}:${CONTAINER_PORT}): Not connected"
        fi
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${YELLOW}Unknown command: ${COMMAND}${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac

