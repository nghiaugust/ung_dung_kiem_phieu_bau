# Dockerfile cho Django Web App (Production)
FROM python:3.12.6-slim

ARG PIP_INDEX_URL=https://pypi.org/simple

# Metadata
LABEL maintainer="domanhnghiaforwork@gmail.com"
LABEL description="UDKPB - Ứng Dụng Kiểm Phiếu Bầu - Django Web Application"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=15 \
    PIP_INDEX_URL=${PIP_INDEX_URL}

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
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libzbar0 \
    # PDF processing
    poppler-utils \
    # LaTeX toolchain for ballot form generation
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-pictures \
    texlive-lang-other \
    # Network utilities for health checks
    netcat-openbsd \
    curl \
    # Cleaning up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy Docker-specific requirements
COPY docker/requirements.web.docker.txt /tmp/requirements.web.docker.txt

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install --retries 15 --timeout 180 --no-build-isolation py-ubjson==0.16.1 && \
    pip install --retries 15 --timeout 180 --prefer-binary -r /tmp/requirements.web.docker.txt

# Copy project files
COPY UDKPB/kiem_phieu_bau /app/kiem_phieu_bau
COPY UDKPB/ai_core /app/ai_core

# Create necessary directories
RUN mkdir -p /app/kiem_phieu_bau/media \
    /app/kiem_phieu_bau/staticfiles \
    /app/kiem_phieu_bau/logs

# Set working directory to Django project
WORKDIR /app/kiem_phieu_bau

# Copy entrypoint script
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Expose port
EXPOSE 8000

# Entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command (web server)
CMD ["gunicorn", "kiem_phieu_bau.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
