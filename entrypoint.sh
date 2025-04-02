#!/bin/bash

# Print out environment variables for debugging
echo "Current working directory: $(pwd)"
echo "Python version: $(python --version)"
echo "Django version: $(python -m django --version)"

# Create a simple Django server script
cat > run_django.py << EOL
import os
os.environ['DEBUG'] = 'True'
os.environ['ALLOWED_HOSTS'] = 'localhost,127.0.0.1,0.0.0.0'

import django
from django.core.management import call_command
django.setup()

print("Starting Django development server...")
call_command('runserver', '0.0.0.0:8000')
EOL

# Run the script
python run_django.py 