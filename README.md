# Hướng dẫn

## 1. Chuẩn bị môi trường

- Cài Python >= 3.8
- Cài pip
- (Khuyến nghị) Tạo virtual environment:
  ```powershell
  python -m venv venv
  .\venv\Scripts\activate
  ```

## 2. Cài đặt các thư viện cần thiết

```powershell
cd UDKPB
pip install -r requirements.txt
```

## 3. Tải model TrOCR

```powershell
cd UDKPB/ballot_processing_system
python -c "from transformers import AutoModelForVision2Seq, AutoTokenizer, AutoProcessor; AutoModelForVision2Seq.from_pretrained('microsoft/trocr-base-printed', cache_dir='model_trocr'); AutoTokenizer.from_pretrained('microsoft/trocr-base-printed', cache_dir='model_trocr'); AutoProcessor.from_pretrained('microsoft/trocr-base-printed', cache_dir='model_trocr')"
```

## 4. Cấu hình file `settings.py`

- Đổi `DEBUG = False` khi chạy production.
- Sửa `ALLOWED_HOSTS` thành domain hoặc IP server thật.
- Thêm dòng sau vào cuối file để collect static files:
  ```python
  STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
  ```
- Kiểm tra thông tin kết nối MySQL cho đúng với server.

## 5. Khởi tạo database

```powershell
cd UDKPB/kiem_phieu_bau
python manage.py migrate
```

## 6. Collect static files

```powershell
cd UDKPB/kiem_phieu_bau
python manage.py collectstatic
```
## 7. Tạo tài khoản admin

```powershell
cd UDKPB/kiem_phieu_bau
python manage.py shell -c "from quan_ly_phieu_bau.models import Account; Account.objects.create_user('admin', password='1', role='admin')"
```
## 8. Chạy server

- Dev:
  ```powershell
  python manage.py runserver 0.0.0.0:8000
  ```
- Production (khuyến nghị dùng gunicorn/uwsgi + nginx)

---

**Lưu ý:**

- Nếu server không cài được `mysqlclient`, có thể thay bằng `pymysql` (và sửa settings).
- Đảm bảo đã mở port 8000 trên server hoặc cấu hình nginx reverse proxy.
