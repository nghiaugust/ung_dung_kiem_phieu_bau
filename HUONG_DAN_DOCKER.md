# 🚀 HƯỚNG DẪN DOCKER CHO NGƯỜI MỚI BẮT ĐẦU

## 📖 DOCKER LÀ GÌ?

**Docker** là công nghệ đóng gói ứng dụng thành "container" - giống như đóng gói toàn bộ nhà (ứng dụng + môi trường) vào một cái hộp. Người khác chỉ cần mở hộp ra là dùng được ngay!

**Lợi ích:**
- ✅ **Không cần cài Python, MySQL, Redis** - Tất cả đã có sẵn trong container
- ✅ **Chạy trên bất kỳ máy nào** - Windows, Mac, Linux đều được
- ✅ **Đồng bộ môi trường** - Dev và Production giống hệt nhau
- ✅ **Deploy dễ dàng** - 1 lệnh là chạy cả hệ thống

---

## 📥 BƯỚC 1: CÀI ĐẶT DOCKER

### Windows:

1. **Tải Docker Desktop:**
   - Truy cập: https://www.docker.com/products/docker-desktop/
   - Click **Download for Windows**
   - Chạy file cài đặt `Docker Desktop Installer.exe`

2. **Cài đặt:**
   - Chấp nhận điều khoản
   - Chọn **Use WSL 2 instead of Hyper-V** (khuyến nghị)
   - Click Install
   - Khởi động lại máy nếu yêu cầu

3. **Mở Docker Desktop:**
   - Tìm và mở **Docker Desktop** từ Start Menu
   - Chờ Docker khởi động (biểu tượng cá voi màu xanh ở taskbar)

4. **Kiểm tra cài đặt:**
   ```powershell
   docker --version
   docker-compose --version
   ```
   
   Kết quả mong đợi:
   ```
   Docker version 24.x.x
   Docker Compose version v2.x.x
   ```

---

## 🛠️ BƯỚC 2: CHUẨN BỊ DỰ ÁN

### Có 2 cách:

#### **Cách 1: Copy toàn bộ source code trực tiếp**

```
ung_dung_kiem_phieu_bau/
├── docker/              ← Các file Docker đã cấu hình sẵn
│   ├── .env.docker      ← Đã cấu hình sẵn passwords
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── ...
├── UDKPB/
│   ├── kiem_phieu_bau/
│   └── ai_core/
│       └── model_yolo_x/
│           └── best.pt  ← Model YOLO có sẵn
└── HUONG_DAN_DOCKER.md  ← File này
```

**Lưu ý:** Copy toàn bộ thư mục, KHÔNG BỎ QUA bất kỳ file nào!

---

#### **Cách 2: Clone từ Git (Khuyến nghị)**

Nếu dự án đã được push lên Git/GitHub:

```powershell
# 1. Clone repository
git clone https://github.com/your-username/ung_dung_kiem_phieu_bau.git
cd ung_dung_kiem_phieu_bau

# 2. Tạo file .env cho Django (nếu chưa có)
# Copy từ .env.example hoặc tạo mới
cd UDKPB/kiem_phieu_bau
copy .env.example .env
# Sửa thông tin trong .env (SECRET_KEY, DB_PASSWORD, etc.)

# 3. Tạo file .env.docker cho Docker (nếu chưa có)
cd ../../docker
copy .env.docker.example .env.docker
# Hoặc sửa trực tiếp file .env.docker có sẵn

# 4. Copy model YOLO (vì đã bị ignore trong Git)
# Download hoặc copy file best.pt vào:
# UDKPB/ai_core/model_yolo_x/best.pt
```

**Lưu ý quan trọng khi clone từ Git:**
- ✅ File `.env` và `.env.docker` thường bị ignore (vì chứa secrets)
- ✅ Model YOLO (`best.pt`) bị ignore (vì file lớn)
- ✅ TrOCR model KHÔNG cần (Docker sẽ tải tự động)

**Checklist sau khi clone:**
- [ ] Đã tạo/cấu hình file `UDKPB/kiem_phieu_bau/.env`
- [ ] Đã tạo/cấu hình file `docker/.env.docker`
- [ ] Đã copy model YOLO vào `UDKPB/ai_core/model_yolo_x/best.pt`

---

## 🚀 BƯỚC 3: CHẠY ỨNG DỤNG (Lần Đầu)

### ⚠️ TRƯỚC KHI CHẠY - KIỂM TRA:

```powershell
# Kiểm tra file .env.docker tồn tại
dir docker\.env.docker

# Kiểm tra model YOLO tồn tại
dir UDKPB\ai_core\model_yolo_x\best.pt

# Nếu thiếu, xem lại BƯỚC 2
```

### Mở PowerShell/Command Prompt:

```powershell
# 1. Di chuyển vào thư mục docker
cd C:\path\to\ung_dung_kiem_phieu_bau\docker

# 2. Build Docker images (lần đầu tiên, mất 10-20 phút)
docker-compose build

# 3. Khởi động tất cả services
docker-compose up -d

# 4. Xem logs để kiểm tra
docker-compose logs -f
```

**Giải thích:**
- `docker-compose build` - Xây dựng images (giống như cài đặt môi trường)
- `docker-compose up -d` - Chạy ứng dụng ở chế độ background
- `docker-compose logs -f` - Xem logs real-time (Ctrl+C để thoát)

### Chờ khởi động:

Bạn sẽ thấy các dòng log:
```
✓ MySQL is up and running!
✓ Redis is up and running!
Running database migrations...
Collecting static files...
Starting application...
```

---

## 🌐 BƯỚC 4: TRUY CẬP ỨNG DỤNG

Sau khi khởi động xong (khoảng 2-3 phút):

### 1. Web Application:
- URL: **http://localhost**
- Hoặc: **http://127.0.0.1**

### 2. Django Admin:
- URL: **http://localhost/admin**
- Username: `admin`
- Password: `admin123`

**⚠️ QUAN TRỌNG:** Đổi password ngay sau lần đầu đăng nhập!

### 3. Celery Monitoring (Flower) - Optional:

Nếu muốn xem tiến trình xử lý ảnh:
```powershell
# Chạy thêm Flower
docker-compose --profile monitoring up -d

# Truy cập: http://localhost:5555
# Username: admin
# Password: FlowerAdmin2026!@#
```

---

## 🔍 CÁC LỆNH QUAN TRỌNG

### Khởi động/Dừng:

```powershell
# Khởi động tất cả
docker-compose up -d

# Dừng tất cả
docker-compose stop

# Dừng và XÓA containers (giữ data)
docker-compose down

# Dừng và XÓA containers + DATA (CẢNH BÁO!)
docker-compose down -v
```

### Xem trạng thái:

```powershell
# Xem containers đang chạy
docker-compose ps

# Xem logs
docker-compose logs -f

# Xem logs của 1 service cụ thể
docker-compose logs -f web
docker-compose logs -f celery-worker
docker-compose logs -f mysql
```

### Restart:

```powershell
# Restart tất cả
docker-compose restart

# Restart 1 service
docker-compose restart web
```

### Update code:

```powershell
# Sau khi sửa code, rebuild và restart
docker-compose build web
docker-compose up -d --force-recreate web
```

---

## 🗃️ QUẢN LÝ DATABASE

### Backup Database:

```powershell
# Backup ra file SQL
docker-compose exec mysql mysqldump -u root -pRootDocker2026!@#Secure udkpb > backup_$(Get-Date -Format "yyyyMMdd_HHmmss").sql
```

### Restore Database:

```powershell
# Restore từ file backup
Get-Content backup_20260112_140000.sql | docker-compose exec -T mysql mysql -u root -pRootDocker2026!@#Secure udkpb
```qua Git/GitHub (Khuyến nghị)

**Người chia sẻ:**
```powershell
# 1. Push code lên Git (đã ignore .env và models)
git add .
git commit -m "Add Docker support"
git push origin main

# 2. Gửi riêng cho người nhận:
#    - File .env.docker (hoặc hướng dẫn tạo)
#    - File best.pt (model YOLO)
```

**Người nhận:**
```powershell
# 1. Cài Docker Desktop
# 2. Clone repository
git clone https://github.com/your-username/repo.git
cd repo

# 3. Copy3: Xuất Docker Images (không cần build)

**Ưu điểm:** Người nhận không cần build (tiết kiệm thời gian)
**Nhược điểm:** File .tar rất lớn (3-5GB)

```powershell
# 1. Build images trên máy của bạn
cd docker
docker-compose build

# 2. Lưu images ra file
docker save -o udkpb_web.tar docker_web:latest
docker save -o udkpb_celery.tar docker_celery-worker:latest

# 3. Copy 2 file .tar + docker-compose.yml + .env.docker cho người khác

# 4. Người nhận load images:
docker load -i udkpb_web.tar
docker load -i udkpb_celery.tar

# 5gười chia sẻ:
# - Nén toàn bộ thư mục thành ZIP
# - Gửi file ZIP cho người khác

# Người nhận chỉ cần:
1. Cài Docker Desktop
2. Giải nén thư mục dự án
3. Chạy: cd docker && docker-compose build

---

## 📦 CHIA SẺ CHO NGƯỜI KHÁC

### Cách 1: Chia sẻ toàn bộ source code

```powershell
# Người nhận chỉ cần:
1. Cài Docker Desktop
2. Copy toàn bộ thư mục dự án
3. Chạy: cd docker && docker-compose up -d
```

### Cách 2: Xuất Docker Images (không cần build)

```powershell
# 1. Lưu images ra file
docker save -o udkpb_web.tar udkpb_web:latest
docker save -o udkpb_celery.tar udkpb_celery:latest

# 2. Copy 2 file .tar cho người khác

# 3. Ngườ4: Push lên Docker Hub (Public/Private)

**Ưu điểm:** Dễ chia sẻ, tự động update
**Nhược điểm:** Cần tài khoản Docker Hub

```powershell
# 1. Đăng ký tài khoản tại https://hub.docker.com
# 2. Login
docker login

# 3. Tag images
docker tag docker_web:latest your-username/udkpb_web:latest
docker tag docker_celery-worker:latest your-username/udkpb_celery:latest

# 4. Push lên Docker Hub
docker push your-username/udkpb_web:latest
docker push your-username/udkpb_celery:latest

# 5. Người khác chỉ cần pull và chạy
docker pull your-username/udkpb_web:latest
docker pull your-username/udkpb_celery:latest
docker-compose up -d
```

---

### 🎯 KHUYẾN NGHỊ THEO TÌNH HUỐNG:

| Tình huống | Phương pháp |
|------------|-------------|
| Làm việc nhóm, có Git | ✅ Cách 1: Push lên Git |
| Gửi cho 1 người, nhanh | Cách 2: ZIP toàn bộ |
| Deploy production | Cách 4: Docker Hub |
| Offline, không có mạng | Cách 3: Export .tar |ker push your-username/udkpb_web:latest
docker push your-username/udkpb_celery:latest

# 5. Người khác chỉ cần pull và chạy
docker pull your-username/udkpb_web:latest
docker pull your-username/udkpb_celery:latest
docker-compose up -d
```

---

## ⚙️ CẤU HÌNH NÂNG CAO

### Scale thêm Celery Workers (xử lý nhiều ảnh cùng lúc):

```powershell
# Chạy thêm worker thứ 2
docker-compose --profile scale up -d

# Hoặc scale thủ công
docker-compose up -d --scale celery-worker=3
```

### Thay đổi port:

Sửa file `docker/.env.docker`:
```bash
WEB_0. File .env.docker không tồn tại

**Lỗi:** `ERROR: Couldn't find env file`

**Giải pháp:**
```powershell
# Tạo file .env.docker từ template
cd docker
copy .env.docker.example .env.docker

# Hoặc tạo thủ công, xem nội dung mẫu tại:
# docker/.env.docker trong source code
```

### 0b. Model YOLO không tồn tại

**Lỗi:** Build thành công nhưng Celery worker bị lỗi khi xử lý ảnh

**Giải pháp:**
```powershell
# Đảm bảo file tồn tại:
dir UDKPB\ai_core\model_yolo_x\best.pt

# Nếu không có, download hoặc copy từ máy khác
# Sau đó rebuild:
docker-compose build celery-worker
docker-compose up -d --force-recreate celery-worker
```

### PORT=8080        # Thay vì 8000
NGINX_HTTP_PORT=8080 # Thay vì 80
```

Sau đó restart:
```powershell
docker-compose down
docker-compose up -d
```

---

## 🐛 XỬ LÝ LỖI THƯỜNG GẶP

### 1. Port đã được sử dụng

**Lỗi:** `Bind for 0.0.0.0:80 failed: port is already allocated`

**Giải pháp:**
```powershell
# Tìm process đang dùng port 80
netstat -ano | findstr :80

# Hoặc đổi port trong .env.docker
NGINX_HTTP_PORT=8080
```

### 2. Container không start

```powershell
# Xem logs chi tiết
docker-compose logs web

# Xem lỗi của container cụ thể
docker logs udkpb_web
```

### 3. MySQL connection refused

```powershell
# Chờ MySQL khởi động xong (30s - 1 phút)
# Xem logs MySQL
docker-compose logs mysql

# Restart MySQL
docker-compose restart mysql
```

### 4. Out of disk space

```powershell
# Xóa images, containers cũ không dùng
docker system prune -a

# Xóa volumes không dùng (CẢNH BÁO: Mất data)
docker volume prune
```

### 5. Celery worker không nhận tasks

```powershell
# Kiểm tra Redis
docker-compose exec redis redis-cli ping
# Kết quả: PONG

# Restart Celery worker
docker-compose restart celery-worker
```

---

## 🔐 BẢO MẬT

### Đổi Passwords (QUAN TRỌNG khi deploy thật):

File `docker/.env.docker`:
```bash
# Django Admin
# Đổi sau khi login: http://localhost/admin

# MySQL
DB_PASSWORD=your-new-strong-password
DB_ROOT_PASSWORD=your-root-password

# Flower
FLOWER_PASSWORD=your-flower-password
```

### Tạo SECRET_KEY mới:

```powershell
docker-compose exec web python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy kết quả vào `SECRET_KEY` trong `.env.docker`

---

## 📚 TÀI LIỆU THAM KHẢO

- Docker Documentation: https://docs.docker.com/
- Docker Compose: https://docs.docker.com/compose/
- Django + Docker: https://docs.djangoproject.com/en/5.0/howto/deployment/


### Trước khi build:
- [ ] Docker Desktop đã khởi động
- [ ] File `docker/.env.docker` tồn tại và đã cấu hình
- [ ] File `UDKPB/ai_core/model_yolo_x/best.pt` tồn tại
- [ ] (Nếu clone từ Git) Đã tạo file `.env` trong `UDKPB/kiem_phieu_bau/`

### Sau khi build xong:
## 🆘 HỖ TRỢ

Nếu gặp vấn đề:

1. **Xem logs chi tiết:**
   ```powershell
   docker-compose logs -f --tail=100
   ```

2. **Restart tất cả:**
   ```powershell
   docker-compose down
   docker-compose up -d
   ```

3. **Xóa và build lại (last resort):**
   ```powershell
   docker-compose down -v
   docker-compose build --no-cache
   docker-compose up -d
   ```

4. **Liên hệ:** domanhnghiaforwork@gmail.com

---

## ✅ CHECKLIST SAU KHI CÀI XONG

- [ ] Docker Desktop đã khởi động
- [ ] `docker-compose ps` hiển thị tất cả containers "Up"
- [ ] Truy cập được http://localhost
- [ ] Login được admin panel (admin/admin123)
- [ ] Đã đổi password admin
- [ ] Đã đổi passwords trong .env.docker (nếu deploy thật)

---

**Chúc bạn thành công! 🎉**
