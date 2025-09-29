#!/usr/bin/env bash
set -euo pipefail

cd /app/UDKPB/kiem_phieu_bau

if [ -n "${DB_HOST:-}" ]; then
  echo "Waiting for DB at $DB_HOST:${DB_PORT:-3306}..."
  for i in {1..60}; do
    nc -z "$DB_HOST" "${DB_PORT:-3306}" && echo "DB is up" && break || true
    echo "DB not ready yet, retry $i..."; sleep 2
  done
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ "${CREATE_ADMIN:-false}" = "true" ]; then
  echo "Ensuring admin user exists..."
  python manage.py shell -c "from quan_ly_phieu_bau.models import Account; \
import os; \
username=os.environ.get('ADMIN_USERNAME','admin'); \
password=os.environ.get('ADMIN_PASSWORD','1'); \
from django.contrib.auth import get_user_model; User=get_user_model(); \
User.objects.filter(username=username).exists() or User.objects.create_user(username, password=password, role='admin')"
fi

exec gunicorn kiem_phieu_bau.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers ${GUNICORN_WORKERS:-2} \
  --threads ${GUNICORN_THREADS:-2} \
  --timeout ${GUNICORN_TIMEOUT:-120}
