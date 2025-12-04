#!/bin/bash

# Print out environment variables for debugging
echo "Current working directory: $(pwd)"
echo "Python version: $(python --version)"
echo "Django version: $(python -m django --version)"

# Run migrations for both databases
echo "Running migrations for default database..."
python manage.py migrate --database=default

echo "Running migrations for store database..."
python manage.py migrate --database=store

# Create a simple Django server script
cat > run_django.py << EOL
import os
import django
from django.core.management import call_command
django.setup()

print("Starting Django development server...")
print(f"DEBUG: {os.getenv('DEBUG', 'Not set')}")
print(f"ALLOWED_HOSTS: {os.getenv('ALLOWED_HOSTS', 'Not set')}")
call_command('runserver', '0.0.0.0:8000')
EOL

# Run the script
python run_django.py 