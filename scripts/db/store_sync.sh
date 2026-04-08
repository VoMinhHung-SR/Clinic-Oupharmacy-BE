#!/usr/bin/env bash
# Store DB: data-only dump (pg_dump custom) or restore + reset_store_sequences.
# Usage:
#   ./store_sync.sh dump [output.dump]
#   ./store_sync.sh restore <dump.dump> [TARGET_POSTGRES_URL]
# Or via: ./db-manager.sh store-dump | store-restore

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/config.sh"
load_env
cd "${PROJECT_ROOT}"

cmd_dump() {
  if [[ -z "${STORE_DATABASE_URL_PG:-}" ]]; then
    echo "Error: set STORE_DATABASE_URL_PG (e.g. in .env) to your local store database URL." >&2
    exit 1
  fi
  local out="${1:-${PROJECT_ROOT}/artifacts/store_data_$(date +%Y%m%d_%H%M%S).dump}"
  mkdir -p "$(dirname "$out")"
  echo "Dumping DATA ONLY from store DB → $out"
  pg_dump "$STORE_DATABASE_URL_PG" \
    --format=custom \
    --data-only \
    --no-owner \
    --file="$out"
  echo "Done. $(du -h "$out" | cut -f1)"
  echo ""
  echo "When the DB container is up and migrated (migrate storeApp --database=store):"
  echo "  ./scripts/db/db-manager.sh store-restore \"$out\""
}

cmd_restore() {
  local dump="${1:?Usage: $0 restore <dump.dump> [TARGET_POSTGRES_URL]}"
  local target="${2:-${STORE_DATABASE_URL_PG:-}}"
  if [[ -z "$target" ]]; then
    echo "Error: pass target URL as second argument or set STORE_DATABASE_URL_PG." >&2
    exit 1
  fi
  if [[ ! -f "$dump" ]]; then
    echo "Error: dump file not found: $dump" >&2
    exit 1
  fi
  echo "Restoring DATA ONLY → target store DB"
  echo "  (ensure migrations were applied on target so tables exist)"
  pg_restore \
    --data-only \
    --no-owner \
    --dbname="$target" \
    "$dump"
  echo ""
  echo "Resetting PostgreSQL sequences (Django storeApp)..."
  STORE_DATABASE_URL_PG="$target" python manage.py reset_store_sequences --database=store
  echo ""
  echo "Done. Verify with a quick insert test or admin if needed."
}

case "${1:-}" in
  dump)   shift; cmd_dump "$@" ;;
  restore) shift; cmd_restore "$@" ;;
  *)
    echo "Usage: $0 dump [output.dump]" >&2
    echo "       $0 restore <dump.dump> [TARGET_POSTGRES_URL]" >&2
    exit 1
    ;;
esac
