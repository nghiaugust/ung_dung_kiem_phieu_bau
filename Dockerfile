FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential default-libmysqlclient-dev pkg-config \
    ffmpeg libsm6 libxext6 libgl1 \
    netcat-openbsd bash git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY UDKPB ./UDKPB
COPY UDKPB/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir gunicorn whitenoise

# Pre-download TrOCR model to match README (local cache)
RUN python - <<"PY"
from transformers import AutoModelForVision2Seq, AutoTokenizer, AutoProcessor
from pathlib import Path
model = 'microsoft/trocr-base-printed'
cache_dir = Path('UDKPB/ballot_processing_system/model_trocr')
cache_dir.mkdir(parents=True, exist_ok=True)
AutoModelForVision2Seq.from_pretrained(model, cache_dir=str(cache_dir))
AutoTokenizer.from_pretrained(model, cache_dir=str(cache_dir))
AutoProcessor.from_pretrained(model, cache_dir=str(cache_dir))
print('TrOCR model downloaded to', cache_dir)
PY

EXPOSE 8000

ENV DJANGO_SETTINGS_MODULE=kiem_phieu_bau.settings \
    PYTHONPATH=/app/UDKPB:/app/UDKPB/kiem_phieu_bau:/app/UDKPB/ballot_processing_system

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /app/UDKPB/kiem_phieu_bau
ENTRYPOINT ["/entrypoint.sh"]
