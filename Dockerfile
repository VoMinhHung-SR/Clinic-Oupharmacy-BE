FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # default-libmysqlclient-dev \
    # pkg-config \
    # default-mysql-client \
    # && rm -rf /var/lib/apt/lists/*
    libpq-dev \
    pkg-config \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Make the entrypoint script executable
RUN chmod +x entrypoint.sh

EXPOSE 8000

# Python/Django runtime environment variables
# These are build-time constants that should not be overridden
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=OUPharmacyManagementApp.settings

# Note: DEBUG and ALLOWED_HOSTS are loaded from .env.production via docker-compose.yml
# Do not hard-code them here to allow environment-specific configuration

# Run Django
CMD ["./entrypoint.sh"]