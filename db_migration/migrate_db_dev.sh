#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if pgloader is installed
if ! command -v pgloader &> /dev/null; then
    echo "pgloader is not installed. Installing..."
    sudo apt-get update
    sudo apt-get install -y pgloader
fi

# Run pgloader with the development configuration file
echo "Starting database migration..."
pgloader "${SCRIPT_DIR}/migration.dev.load"

# Check if migration was successful
if [ $? -eq 0 ]; then
    echo "Migration completed successfully!"
    
    # Run Django migrations to ensure schema is up to date
    echo "Running Django migrations..."
    cd "${SCRIPT_DIR}/.."
    python manage.py migrate
    
    echo "Database migration process completed!"
else
    echo "Migration failed. Please check the error messages above."
    exit 1
fi 