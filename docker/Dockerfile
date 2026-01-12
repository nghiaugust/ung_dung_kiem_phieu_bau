# Dockerfile cho Django Web App (Production)
FROM python:3.12.6-slim

# Metadata
LABEL maintainer="domanhnghiaforwork@gmail.com"
LABEL description="UDKPB - Ứng Dụng Kiểm Phiếu Bầu - Django Web Application"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # MySQL client libraries
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    # Image processing libraries
    libgl1 \
    libglib2.0-0 \
    # PDF processing
    poppler-utils \
    # Network utilities for health checks
    netcat-openbsd \
    curl \
    # Cleaning up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files
COPY UDKPB/requirements.txt /app/requirements.txt
COPY UDKPB/kiem_phieu_bau/celery_requirements.txt /app/celery_requirements.txt

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install -r celery_requirements.txt

# Copy project files
COPY UDKPB/kiem_phieu_bau /app/kiem_phieu_bau
COPY UDKPB/ai_core /app/ai_core

# Create necessary directories
RUN mkdir -p /app/kiem_phieu_bau/media \
    /app/kiem_phieu_bau/staticfiles \
    /app/kiem_phieu_bau/logs

# Set working directory to Django project
WORKDIR /app/kiem_phieu_bau

# Collect static files (will be overridden by entrypoint, but good for cache)
RUN python manage.py collectstatic --noinput || true

# Copy entrypoint script
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command (web server)
CMD ["gunicorn", "kiem_phieu_bau.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
