#!/bin/bash
set -e

echo "========================================"
echo "UDKPB Django Entrypoint Script"
echo "========================================"

# Wait for MySQL to be ready
echo "Waiting for MySQL to be ready..."
while ! nc -z ${DB_HOST:-mysql} ${DB_PORT:-3306}; do
  sleep 1
  echo "MySQL is unavailable - sleeping"
done
echo "✓ MySQL is up and running!"

# Wait for Redis to be ready
echo "Waiting for Redis to be ready..."
while ! nc -z ${REDIS_HOST:-redis} ${REDIS_PORT:-6379}; do
  sleep 1
  echo "Redis is unavailable - sleeping"
done
echo "✓ Redis is up and running!"

# Run database migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Create superuser if not exists (for initial setup)
echo "Creating default superuser (if not exists)..."
python manage.py shell -c "
from account.models import Account
if not Account.objects.filter(username='admin').exists():
    Account.objects.create_superuser('admin', email='admin@udkpb.local', password='admin123')
    print('✓ Superuser created: admin/admin123')
else:
    print('✓ Superuser already exists')
" || echo "Superuser creation skipped"

echo "========================================"
echo "Starting application..."
echo "========================================"

# Execute the main command
exec "$@"
