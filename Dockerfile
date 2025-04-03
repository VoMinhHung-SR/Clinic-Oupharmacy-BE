FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    pkg-config \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Make the entrypoint script executable
RUN chmod +x entrypoint.sh

EXPOSE 8000

# Make sure environment variables are loaded
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=OUPharmacyManagementApp.settings
ENV DEBUG=True
ENV ALLOWED_HOSTS="localhost,127.0.0.1,0.0.0.0"

# Run Django
CMD ["./entrypoint.sh"]