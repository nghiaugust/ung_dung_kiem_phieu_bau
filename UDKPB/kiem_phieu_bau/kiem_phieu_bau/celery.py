"""
Celery configuration for kiem_phieu_bau project
"""
import os
from celery import Celery
from celery.schedules import crontab
from kombu import Queue

# Set default Django settings module for 'celery' program
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kiem_phieu_bau.settings')

app = Celery('kiem_phieu_bau')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related config keys
#   should have a `CELERY_` prefix in settings.py
app.config_from_object('django.conf:settings', namespace='CELERY')

# ==========================================
# Cấu hình Queues riêng biệt cho từng loại task
# ==========================================
app.conf.task_queues = (
    Queue('upload_queue', routing_key='upload.#'),
    Queue('counting_queue', routing_key='counting.#'),
    Queue('default', routing_key='default.#'),  # Queue mặc định cho các task khác
)

# Routing: Chỉ định task nào vào queue nào
app.conf.task_routes = {
    'upload_queue': {'queue': 'upload_queue', 'routing_key': 'upload.process'},
    'counting_queue': {'queue': 'counting_queue', 'routing_key': 'counting.process'},
}

# Default queue nếu task không có routing
app.conf.task_default_queue = 'default'
app.conf.task_default_routing_key = 'default.task'

# ==========================================
# Cấu hình Celery Beat - Periodic Tasks
# ==========================================
app.conf.beat_schedule = {
    'auto-cleanup-checking-timeout-every-3-minutes': {
        'task': 'auto_cleanup_checking_timeout',
        'schedule': 180.0,  # 3 phút = 180 giây
        'options': {
            'queue': 'default',
        }
    },
}

# Load task modules from all registered Django apps
# autodiscover_tasks() sẽ tự động tìm file tasks.py trong mỗi app
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery setup"""
    print(f'Request: {self.request!r}')

