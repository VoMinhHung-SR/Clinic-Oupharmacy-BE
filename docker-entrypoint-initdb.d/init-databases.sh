#!/bin/bash
set -e

# Create main database if not exists
# Note: This script only runs when postgres container starts for the first time (new volume)
# Using environment variables from docker-compose.yml
if [ -z "$DB_PG_NAME_DEFAULT" ]; then
    DB_PG_NAME_DEFAULT="oupharmacydb"
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE $DB_PG_NAME_DEFAULT'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_PG_NAME_DEFAULT')\gexec
EOSQL

# Create store database if not exists
if [ -z "$DB_PG_NAME_STORE" ]; then
    DB_PG_NAME_STORE="oupharmacy_store_db"
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE $DB_PG_NAME_STORE'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_PG_NAME_STORE')\gexec
EOSQL

