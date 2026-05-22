# Hướng Dẫn Cài Đặt

## 1. Chuẩn Bị Môi Trường

```powershell
python -m venv venv
.\venv\Scripts\activate
cd UDKPB
pip install -r requirements.txt
```

## 2. Chuẩn Bị Model AI

Đặt các file model vào đúng thư mục:

- VietNameOCR weights: `UDKPB/ai_core/model_vietnameocr/VietNameOCR/weights/mobilenet_svtr_ctc.pth`
- VietNameOCR config: `UDKPB/ai_core/model_vietnameocr/VietNameOCR/config_mobilenet_svtr_ctc.yml`
- YOLO weights: `UDKPB/ai_core/model_yolo_x/best.pt`

## 3. Cấu Hình `.env`

Tạo file `.env` trong `UDKPB/kiem_phieu_bau` và cấu hình các biến chính:

```env
SECRET_KEY=
ALLOWED_HOSTS=
CSRF_TRUSTED_ORIGINS=

DB_ENGINE=
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=

STATIC_URL=
STATIC_ROOT=
MEDIA_URL=
MEDIA_ROOT=
```

## 4. Khởi Tạo Database

```powershell
cd UDKPB/kiem_phieu_bau
python manage.py migrate
python manage.py collectstatic
```

## 5. Tạo Tài Khoản Admin

```powershell
python manage.py shell -c "from account.models import Account; Account.objects.create_superuser('admin', email='admin@example.com', password='1')"
```

## 6. Chạy Server

Chạy AI server:

```powershell
cd UDKPB/ai_core/ai_server
python run_waitress_ai.py
```

Chạy web server:

```powershell
cd UDKPB/kiem_phieu_bau
python manage.py runserver 0.0.0.0:8000
```

Nếu gặp lỗi `mysqlclient`, có thể chuyển sang `pymysql` và cập nhật cấu hình database tương ứng.
