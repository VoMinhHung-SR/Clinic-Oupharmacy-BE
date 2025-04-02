#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # env_file = '.env.local' if os.path.exists('.env.local') else '.env'
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OUPharmacyManagementApp.settings')
    # Make sure DEBUG is set to True
    os.environ['DEBUG'] = 'True'
    os.environ['ALLOWED_HOSTS'] = 'localhost,127.0.0.1,0.0.0.0'
    # os.environ['DJANGO_ENV_FILE'] = env_file
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
