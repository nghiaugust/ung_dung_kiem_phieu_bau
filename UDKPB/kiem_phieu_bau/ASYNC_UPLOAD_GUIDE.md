# Hướng Dẫn Cấu Hình Asynchronous Upload với Celery + Redis

## Tổng Quan

API `api_upload_ballots_batch` đã được refactor từ **Synchronous** sang **Asynchronous** để cải thiện hiệu suất và trải nghiệm người dùng.

### Trước (Synchronous):
```
Client Upload → Verify → Làm phẳng ảnh (30s) → Cắt ô (20s) → Lưu DB → Response
                         ↑ Client bị "treo" chờ đợi ~50s/ảnh
```

### Sau (Asynchronous):
```
Client Upload → Verify → Đọc QR → Lưu file tạm → Đẩy task vào Redis → Response ngay (2s)
                                                          ↓
                                            Celery Worker xử lý ảnh trong background
```

## Các Thay Đổi

### 1. Model Ballot (ballot/models.py)
Đã thêm 2 trường mới:
- `process_status`: Trạng thái xử lý ('pending', 'processing', 'completed', 'failed')
- `process_error`: Lưu lỗi nếu xử lý thất bại

### 2. Celery Task (ballot/task_upload.py)
File mới chứa task `process_ballot_image_task` xử lý:
- Làm phẳng ảnh
- Cắt các ô phiếu bầu
- Cập nhật trạng thái

### 3. API Views (api/views.py)
Hàm `api_upload_ballots_batch` đã được refactor:
- Chỉ verify chữ ký và đọc QR code (nhanh)
- Lưu file tạm và đẩy task vào queue
- Trả về ngay với status code 202 (Accepted)

## Cài Đặt & Cấu Hình

### Bước 1: Cài đặt Redis
```powershell
# Download Redis for Windows từ: https://github.com/microsoftarchive/redis/releases
# Hoặc dùng WSL/Docker
# Hoặc cài qua Chocolatey:
choco install redis-64

# Khởi động Redis
redis-server
```

### Bước 2: Cài đặt thư viện Python
```powershell
cd c:\HocTap\DATN\do_an\ung_dung_kiem_phieu_bau\UDKPB\kiem_phieu_bau
pip install celery redis django-celery-results
```

### Bước 3: Tạo file cấu hình Celery
Tạo file `kiem_phieu_bau/celery.py`:
```python
import os
from celery import Celery

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kiem_phieu_bau.settings')

app = Celery('kiem_phieu_bau')

# Load config from Django settings với prefix 'CELERY_'
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks từ tất cả các app trong INSTALLED_APPS
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
```

### Bước 4: Cập nhật `kiem_phieu_bau/__init__.py`
```python
# Import Celery app để Django load nó khi start
from .celery import app as celery_app

__all__ = ('celery_app',)
```

### Bước 5: Thêm cấu hình vào `settings.py`
```python
# Celery Configuration
CELERY_BROKER_URL = 'redis://localhost:6379/0'  # Redis URL
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Ho_Chi_Minh'

# Optional: Store task results in database
INSTALLED_APPS += ['django_celery_results']
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'django-cache'
```

### Bước 6: Chạy migrations
```powershell
# Migration cho ballot model (process_status, process_error)
python manage.py makemigrations ballot

# Migration cho django_celery_results (nếu dùng)
python manage.py migrate
```

## Khởi Động Hệ Thống

### Terminal 1: Khởi động Redis
```powershell
redis-server
```

### Terminal 2: Khởi động Django
```powershell
cd c:\HocTap\DATN\do_an\ung_dung_kiem_phieu_bau\UDKPB\kiem_phieu_bau
python manage.py runserver
```

### Terminal 3: Khởi động Celery Worker
```powershell
cd c:\HocTap\DATN\do_an\ung_dung_kiem_phieu_bau\UDKPB\kiem_phieu_bau

# Windows (phải dùng eventlet)
pip install eventlet
celery -A kiem_phieu_bau worker --pool=eventlet -l info

# Linux/Mac
celery -A kiem_phieu_bau worker -l info
```

### Terminal 4 (Optional): Celery Flower - Web Monitoring
```powershell
pip install flower
celery -A kiem_phieu_bau flower

# Truy cập: http://localhost:5555
```

## Kiểm Tra Hoạt Động

### 1. Upload phiếu bầu
```bash
POST /api/polls/<poll_id>/upload-batch/
```

Response ngay lập tức:
```json
{
  "success": true,
  "total": 10,
  "accepted": 10,
  "rejected": 0,
  "message": "Đã nhận 10 phiếu bầu. Hệ thống đang xử lý...",
  "results": [
    {
      "filename": "ballot1.jpg",
      "success": true,
      "ballot_id": 123,
      "process_status": "pending",
      "message": "Đã tiếp nhận, đang chờ xử lý"
    }
  ]
}
```

### 2. Kiểm tra trạng thái (tạo API mới)
Tạo API endpoint mới để check status:
```python
@require_api_token
@require_http_methods(["GET"])
def api_ballot_status(request, ballot_id):
    """GET /api/ballots/<ballot_id>/status/"""
    try:
        ballot = Ballot.objects.get(ballot_id=ballot_id)
        return JsonResponse({
            'ballot_id': ballot.ballot_id,
            'process_status': ballot.process_status,
            'process_error': ballot.process_error,
            'has_image': bool(ballot.ballot_image),
            'timestamp': ballot.timestamp.isoformat() if ballot.timestamp else None
        })
    except Ballot.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
```

### 3. Monitor Celery tasks
- Kiểm tra logs ở terminal Celery Worker
- Hoặc dùng Flower: http://localhost:5555

## Debug & Troubleshooting

### Kiểm tra Redis hoạt động
```powershell
redis-cli ping
# Response: PONG
```

### Kiểm tra Celery kết nối Redis
```powershell
celery -A kiem_phieu_bau inspect ping
```

### Xem danh sách tasks đang chờ
```powershell
celery -A kiem_phieu_bau inspect active
```

### Xem registered tasks
```powershell
celery -A kiem_phieu_bau inspect registered
```

### Logs
- Celery worker logs: Terminal 3
- Django logs: Terminal 2
- Redis logs: Terminal 1

## Production Deployment

### Dùng Supervisor (Linux)
```ini
[program:celery-worker]
command=/path/to/venv/bin/celery -A kiem_phieu_bau worker -l info
directory=/path/to/project
user=www-data
autostart=true
autorestart=true
```

### Dùng systemd (Linux)
```ini
[Unit]
Description=Celery Worker
After=network.target redis.service

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=/path/to/project
ExecStart=/path/to/venv/bin/celery -A kiem_phieu_bau worker -l info

[Install]
WantedBy=multi-user.target
```

## Monitoring & Scaling

### Tăng số worker
```powershell
# Chạy nhiều worker song song
celery -A kiem_phieu_bau worker -l info --concurrency=4
```

### Priority Queue (nếu cần)
```python
# settings.py
CELERY_TASK_ROUTES = {
    'ballot.task_upload.process_ballot_image_task': {'queue': 'image_processing'},
}

# Chạy worker cho queue cụ thể
celery -A kiem_phieu_bau worker -Q image_processing -l info
```

## Lợi Ích

1. **Giảm thời gian chờ**: Client chỉ chờ 2-3s thay vì 50s/ảnh
2. **Không block UI**: Mobile app không bị "đơ" khi upload
3. **Retry tự động**: Celery tự retry nếu task fail
4. **Scalable**: Có thể thêm nhiều worker để xử lý song song
5. **Monitor dễ dàng**: Flower UI để theo dõi tasks
6. **Error handling tốt hơn**: Lỗi được log rõ ràng trong `process_error`

## Lưu Ý

- File tạm được lưu bởi API, và được xóa bởi Celery task sau khi xử lý
- Nếu Celery worker down, tasks sẽ được giữ trong Redis queue
- Nên set timeout cho task để tránh task chạy mãi mãi
- Production nên dùng Supervisor/systemd để tự động restart worker
