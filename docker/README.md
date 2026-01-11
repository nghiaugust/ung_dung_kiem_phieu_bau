# UDKPB - Docker Production Deployment

Hướng dẫn triển khai ứng dụng Kiểm Phiếu Bầu với Docker (Production Ready).

## 📋 Yêu Cầu Hệ Thống

- Docker Engine 20.10+
- Docker Compose 2.0+
- RAM: ≥ 8GB (khuyến nghị 16GB cho AI processing)
- Disk: ≥ 50GB (cho database, media, models)
- CPU: ≥ 4 cores

## 🏗️ Kiến Trúc Hệ Thống

```
┌─────────────────────────────────────────────────────────┐
│                      Nginx (Port 80/443)                │
│              (Reverse Proxy + Static Files)             │
└──────────────────────┬──────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┬────────────────────┐
         ▼                           ▼                    ▼
┌─────────────────┐        ┌──────────────────┐   ┌─────────────┐
│   Django Web    │        │  Celery Worker 1 │   │   Flower    │
│   (Gunicorn)    │        │  (AI Processing) │   │ (Monitoring)│
│   Port 8000     │        └──────────────────┘   │  Port 5555  │
└────────┬────────┘                 │              └─────────────┘
         │                          │
         │        ┌─────────────────┴───────────────┐
         │        │      Celery Worker 2 (Scale)    │
         │        │      (AI Processing)            │
         │        └─────────────────────────────────┘
         │                          │
         └──────────────┬───────────┴─────────┬─────────────┐
                        ▼                     ▼             ▼
                ┌──────────────┐      ┌──────────┐   ┌───────────┐
                │    MySQL     │      │  Redis   │   │  Volumes  │
                │   Port 3306  │      │ Port 6379│   │  (Media)  │
                └──────────────┘      └──────────┘   └───────────┘
```

## 🚀 Hướng Dẫn Triển Khai

### Bước 1: Chuẩn Bị Environment Variables

```bash
cd docker/
cp .env.docker .env.docker.local
```

Sửa file `.env.docker.local`:
```bash
# Thay đổi SECRET_KEY
SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')

# Thay đổi passwords
DB_PASSWORD=your-strong-password
DB_ROOT_PASSWORD=your-root-password

# Thay đổi domain
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### Bước 2: Build Docker Images

```bash
# Build tất cả services
docker-compose build

# Hoặc build từng service riêng
docker-compose build web
docker-compose build celery-worker
```

### Bước 3: Khởi Động Hệ Thống

**Cấu hình cơ bản (Web + Celery + DB + Redis + Nginx):**
```bash
docker-compose up -d
```

**Với monitoring (thêm Flower):**
```bash
docker-compose --profile monitoring up -d
```

**Với scheduler (thêm Celery Beat):**
```bash
docker-compose --profile beat up -d
```

**Scale thêm Celery worker:**
```bash
docker-compose --profile scale up -d
```

**Full production (tất cả services):**
```bash
docker-compose --profile monitoring --profile beat --profile scale up -d
```

### Bước 4: Kiểm Tra Hệ Thống

```bash
# Xem logs tất cả services
docker-compose logs -f

# Xem logs từng service
docker-compose logs -f web
docker-compose logs -f celery-worker
docker-compose logs -f mysql

# Kiểm tra trạng thái services
docker-compose ps

# Kiểm tra health check
docker-compose ps | grep healthy
```

### Bước 5: Truy Cập Ứng Dụng

- **Web Application**: http://localhost hoặc http://yourdomain.com
- **Admin Panel**: http://localhost/admin
  - Username: `admin`
  - Password: `admin123` (đổi ngay sau lần đầu đăng nhập!)
- **Flower Monitoring**: http://localhost:5555 (nếu bật profile monitoring)
  - Username: `admin`
  - Password: `admin123`

## 🔧 Quản Lý & Vận Hành

### Migrations

```bash
# Chạy migrations
docker-compose exec web python manage.py migrate

# Tạo migrations mới
docker-compose exec web python manage.py makemigrations
```

### Tạo Superuser

```bash
docker-compose exec web python manage.py createsuperuser
```

### Collect Static Files

```bash
docker-compose exec web python manage.py collectstatic --noinput
```

### Backup Database

```bash
# Backup
docker-compose exec mysql mysqldump -u root -p${DB_ROOT_PASSWORD} udkpb > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore
docker-compose exec -T mysql mysql -u root -p${DB_ROOT_PASSWORD} udkpb < backup_20260112_143000.sql
```

### Restart Services

```bash
# Restart tất cả
docker-compose restart

# Restart từng service
docker-compose restart web
docker-compose restart celery-worker
docker-compose restart nginx
```

### Stop & Remove

```bash
# Stop services
docker-compose stop

# Stop và remove containers
docker-compose down

# Remove containers + volumes (CẢNH BÁO: Xóa data)
docker-compose down -v
```

### Xem Logs Real-time

```bash
# Tất cả services
docker-compose logs -f

# Chỉ web
docker-compose logs -f web

# Chỉ celery worker
docker-compose logs -f celery-worker

# 100 dòng cuối
docker-compose logs --tail=100 web
```

### Scale Celery Workers

```bash
# Scale lên 3 workers
docker-compose up -d --scale celery-worker=3

# Hoặc dùng worker-2 với profile
docker-compose --profile scale up -d
```

## 🔐 Bảo Mật Production

### 1. SSL/TLS Certificate (HTTPS)

```bash
# Sử dụng Let's Encrypt
sudo apt-get install certbot
sudo certbot certonly --standalone -d yourdomain.com

# Copy certificates
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem docker/ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem docker/ssl/key.pem

# Uncomment SSL config trong nginx-site.conf
```

### 2. Đổi Passwords Mặc Định

```bash
# Django admin password
docker-compose exec web python manage.py changepassword admin

# MySQL root password
docker-compose exec mysql mysql -u root -p
> ALTER USER 'root'@'%' IDENTIFIED BY 'new_strong_password';

# Flower password (trong .env.docker)
FLOWER_PASSWORD=your-new-password
```

### 3. Firewall Rules

```bash
# Chỉ mở port 80, 443
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Không mở port 3306, 6379, 8000 ra ngoài
```

## 📊 Monitoring

### Flower (Celery Tasks)
- URL: http://localhost:5555
- Xem real-time tasks, workers, queues
- Monitor memory, CPU usage

### Docker Stats

```bash
# Real-time resource usage
docker stats

# Specific container
docker stats udkpb_celery_worker
```

### Logs Analysis

```bash
# Tìm errors
docker-compose logs web | grep ERROR

# Tìm slow queries
docker-compose logs web | grep "Slow query"
```

## 🐛 Troubleshooting

### 1. Container không start

```bash
# Xem logs
docker-compose logs web

# Xem chi tiết
docker-compose ps
docker inspect udkpb_web
```

### 2. Database connection error

```bash
# Kiểm tra MySQL
docker-compose exec mysql mysql -u root -p -e "SHOW DATABASES;"

# Kiểm tra network
docker-compose exec web ping mysql
```

### 3. Celery worker không nhận tasks

```bash
# Kiểm tra Redis
docker-compose exec redis redis-cli ping

# Kiểm tra Celery
docker-compose exec celery-worker celery -A kiem_phieu_bau inspect ping
```

### 4. Static files không load

```bash
# Collect lại static
docker-compose exec web python manage.py collectstatic --noinput

# Restart nginx
docker-compose restart nginx
```

### 5. Permission errors

```bash
# Fix permissions
docker-compose exec web chown -R appuser:appuser /app/kiem_phieu_bau/media
docker-compose exec web chmod -R 755 /app/kiem_phieu_bau/media
```

## 🔄 Update & Deploy

```bash
# 1. Pull code mới
git pull origin main

# 2. Rebuild images
docker-compose build

# 3. Stop old containers
docker-compose down

# 4. Start new containers
docker-compose up -d

# 5. Run migrations
docker-compose exec web python manage.py migrate

# 6. Collect static
docker-compose exec web python manage.py collectstatic --noinput
```

## 📈 Performance Tuning

### Tăng số Celery Workers

```bash
# Trong docker-compose.yml, sửa concurrency
command: >
  celery -A kiem_phieu_bau worker
  --pool=gevent
  --concurrency=20  # Tăng từ 10 lên 20
```

### Tăng Gunicorn Workers

```bash
# Trong Dockerfile hoặc docker-compose.yml
command: ["gunicorn", ..., "--workers", "8"]  # Tăng từ 4 lên 8
```

### Redis Memory Limit

```bash
# Trong docker-compose.yml
command: redis-server --maxmemory 1gb --maxmemory-policy allkeys-lru
```

## 📝 Notes

- **Volumes**: Data được lưu trong Docker volumes, không bị mất khi restart
- **Networks**: Tất cả services trong cùng network `udkpb_network`
- **Health Checks**: Tự động restart nếu service unhealthy
- **Auto Restart**: `restart: unless-stopped` cho tất cả services
- **Logs**: Xem logs để debug, không dùng DEBUG=True trên production

## 🆘 Support

- Email: domanhnghiaforwork@gmail.com
- Documentation: ../README.md
- Issues: GitHub Issues

---

**Lưu ý Quan Trọng**:
1. Đổi tất cả passwords mặc định
2. Dùng HTTPS (SSL/TLS) cho production
3. Backup database thường xuyên
4. Monitor resource usage (CPU, RAM, Disk)
5. Giới hạn upload file size nếu cần
