#!/bin/bash
set -e

echo "========================================"
echo "UDKPB Django Entrypoint Script"
echo "========================================"

echo "Waiting for MySQL to be ready..."
while ! nc -z ${DB_HOST:-mysql} ${DB_PORT:-3306}; do
  sleep 1
  echo "MySQL is unavailable - sleeping"
done
echo "MySQL is up and running."

echo "Waiting for Redis to be ready..."
while ! nc -z ${REDIS_HOST:-redis} ${REDIS_PORT:-6379}; do
  sleep 1
  echo "Redis is unavailable - sleeping"
done
echo "Redis is up and running."

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Running database migrations..."
  python manage.py migrate --noinput
else
  echo "Skipping database migrations (RUN_MIGRATIONS=0)"
fi

if [ "${COLLECTSTATIC_ON_START:-1}" = "1" ]; then
  echo "Collecting static files..."
  if [ "${COLLECTSTATIC_CLEAR:-0}" = "1" ]; then
    python manage.py collectstatic --noinput --clear
  else
    python manage.py collectstatic --noinput
  fi
else
  echo "Skipping collectstatic (COLLECTSTATIC_ON_START=0)"
fi

if [ "${CREATE_DEFAULT_SUPERUSER:-1}" = "1" ]; then
  echo "Creating default superuser (if not exists)..."
  python manage.py shell -c "
from account.models import Account
if not Account.objects.filter(username='admin').exists():
    Account.objects.create_superuser('admin', email='admin@udkpb.local', password='admin123')
    print('Superuser created: admin/admin123')
else:
    print('Superuser already exists')
" || echo "Superuser creation skipped"
else
  echo "Skipping default superuser creation (CREATE_DEFAULT_SUPERUSER=0)"
fi

echo "========================================"
echo "Starting application..."
echo "========================================"

exec "$@"
