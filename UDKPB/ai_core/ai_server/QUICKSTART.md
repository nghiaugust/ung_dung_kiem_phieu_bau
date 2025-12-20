# Quick Start Guide - AI Server

## 1. Khởi động server

```bash
cd C:\HocTap\DATN\ung_dung_kiem_phieu_bau\UDKPB\ai_core\ai_server
python manage.py runserver 0.0.0.0:8080
```

Server sẽ:

- Load TrOCR model vào bộ nhớ
- Load YOLO model vào bộ nhớ
- Sẵn sàng xử lý request

## 2. Kiểm tra server

Mở browser và truy cập:

- Health check: http://localhost:8080/api/health/
- Model info: http://localhost:8080/api/info/

## 3. Test API

```bash
# Chạy test script
python test_api.py
```

## 4. Sử dụng API

### TrOCR - Nhận diện tên

```bash
curl -X POST http://localhost:8080/api/trocr/recognize/ \
  -F "images=@image1.jpg" \
  -F "images=@image2.jpg"
```

### YOLO - Detect dấu X

```bash
curl -X POST http://localhost:8080/api/yolo/detect/ \
  -F "images=@checkbox1.jpg" \
  -F "images=@checkbox2.jpg"
```

## 5. Tích hợp vào code

```python
import requests

# TrOCR
files = [('images', open('name1.jpg', 'rb')),
         ('images', open('name2.jpg', 'rb'))]
response = requests.post('http://localhost:8080/api/trocr/recognize/', files=files)
result = response.json()

# YOLO
files = [('images', open('checkbox1.jpg', 'rb')),
         ('images', open('checkbox2.jpg', 'rb'))]
response = requests.post('http://localhost:8080/api/yolo/detect/', files=files)
result = response.json()
```

## Troubleshooting

### Port đã được sử dụng

```bash
# Đổi sang port khác
python manage.py runserver 0.0.0.0:8001
```

### Models không load được

- Kiểm tra đường dẫn models trong UDKPB/ai_core/
  - model_trocr/models--microsoft--trocr-base-printed/
  - model_yolo_x/best.pt

### Out of memory

- Giảm batch size
- Restart server

Xem thêm chi tiết trong [README.md](README.md)
