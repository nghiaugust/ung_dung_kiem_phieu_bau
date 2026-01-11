# HƯỚNG DẪN KHỞI ĐỘNG HỆ THỐNG ASYNC UPLOAD

## ✅ Đã Hoàn Thành

- ✅ Cài đặt Redis (port 6379)
- ✅ Cài đặt các package Python (celery, redis, eventlet)
- ✅ Thêm cấu hình Celery vào settings.py
- ✅ Thêm biến môi trường vào .env
- ✅ Tạo Celery app (kiem_phieu_bau/celery.py)
- ✅ Cập nhật __init__.py để load Celery
- ✅ Tạo task xử lý ảnh (ballot/task_upload.py)
- ✅ Refactor API upload_ballots_batch
- ✅ Thêm API check status (ballot_status, ballot_status_batch)
- ✅ Chạy migrations

## 🚀 CÁCH CHẠY HỆ THỐNG (3 TERMINALS)

### Terminal 1: Redis Server
```powershell
# Khởi động Redis
redis-server

# Hoặc nếu Redis được cài dưới dạng service:
net start Redis
```

**Kiểm tra Redis hoạt động:**
```powershell
redis-cli ping
# Kết quả: PONG
```

---

### Terminal 2: Django Server
```powershell
cd C:\HocTap\DATN\do_an\ung_dung_kiem_phieu_bau\UDKPB\kiem_phieu_bau

# Chạy migrations (chỉ lần đầu)
python manage.py migrate

# Khởi động Django
python manage.py runserver
```

**Server sẽ chạy tại:** `http://localhost:8000`

---

### Terminal 3: Celery Worker
```powershell
cd C:\HocTap\DATN\do_an\ung_dung_kiem_phieu_bau\UDKPB\kiem_phieu_bau

# ===== CHỌN 1 TRONG 3 CÁCH SAU =====

# CÁCH 1: SOLO Pool (Đơn giản - Khuyến nghị cho Dev/Python 3.12)
celery -A kiem_phieu_bau worker --pool=solo -l info

# CÁCH 2: GEVENT Pool (Nhanh - Khuyến nghị cho Production)
# pip install gevent
celery -A kiem_phieu_bau worker --pool=gevent --concurrency=10 -l info

# CÁCH 3: THREADS Pool (Trung bình - Windows-friendly)
# celery -A kiem_phieu_bau worker --pool=threads --concurrency=4 -l info

# CÁCH 4: EVENTLET Pool (Chỉ dùng với Python ≤ 3.11)
# pip install eventlet
# celery -A kiem_phieu_bau worker --pool=eventlet -l info

# Linux/Mac (nếu deploy production):
# celery -A kiem_phieu_bau worker -l info
```

**Celery worker sẽ:**
- Kết nối tới Redis
- Lắng nghe task queue
- Xử lý task `process_ballot_image_task` khi có

---

### Terminal 4 (Optional): Celery Flower - Monitoring UI
```powershell
cd C:\HocTap\DATN\do_an\ung_dung_kiem_phieu_bau\UDKPB\kiem_phieu_bau

celery -A kiem_phieu_bau flower
```

**Flower UI:** `http://localhost:5555`

---

## 🧪 KIỂM TRA HỆ THỐNG

### 1. Test Celery kết nối Redis
```powershell
cd C:\HocTap\DATN\do_an\ung_dung_kiem_phieu_bau\UDKPB\kiem_phieu_bau

# Kiểm tra worker có hoạt động không
celery -A kiem_phieu_bau inspect ping

# Xem danh sách registered tasks
celery -A kiem_phieu_bau inspect registered

# Kết quả mong đợi:
# - ballot.task_upload.process_ballot_image_task
```

### 2. Test Upload API (Async)
```bash
# Upload ballots với signatures
POST http://localhost:8000/api/polls/1/upload-batch/
Authorization: Bearer <your_token>

# Response ngay lập tức (không chờ xử lý ảnh):
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

### 3. Check Status của Ballot
```bash
# Kiểm tra 1 ballot
GET http://localhost:8000/api/ballots/123/status/
Authorization: Bearer <your_token>

# Response:
{
  "success": true,
  "ballot_id": 123,
  "process_status": "completed",  # pending/processing/completed/failed
  "process_error": null,
  "has_image": true,
  "timestamp": "2026-01-11T10:30:00+07:00",
  "poll_id": 1,
  "is_checked": false,
  "is_valid": true
}
```

```bash
# Kiểm tra nhiều ballots cùng lúc
POST http://localhost:8000/api/ballots/status-batch/
Authorization: Bearer <your_token>
Body: {
  "ballot_ids": [123, 124, 125]
}

# Response:
{
  "success": true,
  "total": 3,
  "requested": 3,
  "ballots": [
    {
      "ballot_id": 123,
      "process_status": "completed",
      "has_image": true
    },
    {
      "ballot_id": 124,
      "process_status": "processing",
      "has_image": false
    },
    {
      "ballot_id": 125,
      "process_status": "failed",
      "process_error": "Không đủ 4 markers",
      "has_image": false
    }
  ]
}
```

---

## 📊 MONITORING

### Xem logs của Celery Worker (Terminal 3)
```
[2026-01-11 10:30:15,123: INFO/MainProcess] Received task: ballot.task_upload.process_ballot_image_task[abc-123]
[2026-01-11 10:30:45,456: INFO/ForkPoolWorker-1] [TASK] Bắt đầu làm phẳng ảnh cho ballot_id=123
[2026-01-11 10:31:15,789: INFO/ForkPoolWorker-1] [TASK] Hoàn thành cắt cells cho ballot_id=123
[2026-01-11 10:31:16,000: INFO/ForkPoolWorker-1] Task ballot.task_upload.process_ballot_image_task[abc-123] succeeded
```

### Xem active tasks
```powershell
celery -A kiem_phieu_bau inspect active
```

### Xem task statistics
```powershell
celery -A kiem_phieu_bau inspect stats
```

---

## ⚠️ TROUBLESHOOTING

### Lỗi: Redis connection refused
```
Nguyên nhân: Redis chưa chạy
Giải pháp: Khởi động Redis ở Terminal 1
```

### Lỗi: ModuleNotFoundError: No module named 'celery'
```
Nguyên nhân: Chưa cài celery
Giải pháp: pip install -r celery_requirements.txt
```

### Lỗi: Task không được xử lý
```
Nguyên nhân: Celery worker chưa chạy
Giải pháp: Khởi động Celery worker ở Terminal 3
```

### Lỗi: eventlet không tương thích Python 3.12
```
Lỗi: AttributeError: module 'ssl' has no attribute 'wrap_socket'

Nguyên nhân: eventlet không hỗ trợ Python 3.12
Giải pháp: Dùng SOLO, GEVENT hoặc THREADS pool

# SOLO Pool (Đơn giản nhất)
celery -A kiem_phieu_bau worker --pool=solo -l info

# GEVENT Pool (Tốt nhất)
pip install gevent
celery -A kiem_phieu_bau worker --pool=gevent --concurrency=10 -l info

# THREADS Pool
celery -A kiem_phieu_bau worker --pool=threads --concurrency=4 -l info
```

### Task bị stuck ở "pending"
```
Kiểm tra:
1. Celery worker có đang chạy không? (Terminal 3)
2. Redis có hoạt động không? (redis-cli ping)
3. Task có được registered không? (celery -A kiem_phieu_bau inspect registered)
```

---

## 🎯 WORKFLOW HOÀN CHỈNH

### Client (Mobile App):
1. Upload 10 ảnh + signatures qua API
2. Nhận response ngay (2-5s):
   - `accepted: 10`
   - Mỗi ballot có `process_status: "pending"`
3. Poll API `/ballots/status-batch/` mỗi 5 giây để check status
4. Hiển thị:
   - ✅ Completed (xanh)
   - ⏳ Processing (vàng)
   - ⏸️ Pending (xám)
   - ❌ Failed (đỏ - hiển thị lỗi)

### Server:
1. **API (Sync - nhanh):**
   - Verify signatures (bắt buộc)
   - Đọc QR code để lấy ballot_id
   - Lưu file tạm
   - Set `process_status = 'pending'`
   - Đẩy task vào Redis
   - Response 202 Accepted

2. **Worker (Async - nặng):**
   - Lấy task từ Redis queue
   - Làm phẳng ảnh (~30s)
   - Cắt cells (~20s)
   - Update `process_status = 'completed'`
   - Xóa temp files

---

## 📋 CHECKLIST TRƯỚC KHI SỬ DỤNG

- [ ] Redis đang chạy (Terminal 1)
- [ ] Django server đang chạy (Terminal 2)
- [ ] Celery worker đang chạy (Terminal 3)
- [ ] Test `redis-cli ping` → PONG
- [ ] Test `celery -A kiem_phieu_bau inspect ping` → pong
- [ ] Migrations đã chạy xong
- [ ] .env file có CELERY_BROKER_URL và CELERY_RESULT_BACKEND

---

## 🚀 PRODUCTION DEPLOYMENT

### Linux/Ubuntu với Supervisor:

**1. Cài Supervisor:**
```bash
sudo apt-get install supervisor
```

**2. Tạo config file `/etc/supervisor/conf.d/celery.conf`:**
```ini
[program:celery-worker]
command=/path/to/venv/bin/celery -A kiem_phieu_bau worker -l info
directory=/path/to/kiem_phieu_bau
user=www-data
autostart=true
autorestart=true
stdout_logfile=/var/log/celery/worker.log
stderr_logfile=/var/log/celery/worker-error.log
```

**3. Khởi động:**
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start celery-worker
sudo supervisorctl status
```

---

**Hoàn tất!** Hệ thống async upload đã sẵn sàng 🎉
