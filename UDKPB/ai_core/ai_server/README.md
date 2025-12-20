# AI Server API Documentation

API server cho TrOCR và YOLO models với khả năng xử lý batch tối ưu.

## Tính năng

- ✅ **Model caching**: Models được load vào bộ nhớ khi server khởi động, không cần load lại
- ✅ **Batch processing**: Xử lý nhiều ảnh cùng lúc để tăng tốc
- ✅ **GPU support**: Tự động sử dụng GPU nếu có
- ✅ **REST API**: Dễ dàng tích hợp với bất kỳ hệ thống nào
- ✅ **Error handling**: Xử lý lỗi tốt, trả về kết quả cho từng ảnh

## Cài đặt

### 1. Cài đặt dependencies

```bash
pip install django
pip install torch torchvision
pip install transformers
pip install ultralytics
pip install pillow
```

### 2. Cấu trúc thư mục

Đảm bảo cấu trúc như sau:

```
UDKPB/
├── ai_core/
│   ├── ai_server/          # Django project
│   │   ├── manage.py
│   │   ├── ai_server/      # Settings
│   │   └── api/            # API app
│   │       ├── model_services.py
│   │       ├── views.py
│   │       ├── urls.py
│   │       └── apps.py
│   ├── model_trocr/        # TrOCR model
│   │   └── models--microsoft--trocr-base-printed/
│   └── model_yolo_x/       # YOLO model
│       └── best.pt
```

## Khởi động server

```bash
cd UDKPB/ai_core/ai_server
python manage.py runserver 0.0.0.0:8080
```

Server sẽ khởi động và tự động load models vào bộ nhớ.

## API Endpoints

### 1. Health Check

Kiểm tra trạng thái server và models.

**Request:**

```http
GET /api/health/
```

**Response:**

```json
{
  "status": "healthy",
  "services": {
    "trocr": true,
    "yolo": true
  }
}
```

### 2. Model Info

Xem thông tin về models đã load.

**Request:**

```http
GET /api/info/
```

**Response:**

```json
{
  "models": {
    "trocr": {
      "loaded": true,
      "device": "GPU"
    },
    "yolo": {
      "loaded": true,
      "device": "GPU"
    }
  },
  "system": {
    "cuda_available": true,
    "cuda_device_count": 1
  }
}
```

### 3. TrOCR - Nhận diện Text

Nhận diện text (tên người) từ ảnh.

**Request:**

```http
POST /api/trocr/recognize/
Content-Type: multipart/form-data

Form data:
- images: [file1.jpg, file2.jpg, ...]
```

**Response:**

```json
{
  "success": true,
  "count": 2,
  "results": [
    {
      "filename": "image1.jpg",
      "text": "Nguyen Van A",
      "status": "success"
    },
    {
      "filename": "image2.jpg",
      "text": "Tran Thi B",
      "status": "success"
    }
  ]
}
```

**Ví dụ với cURL:**

```bash
curl -X POST http://localhost:8080/api/trocr/recognize/ \
  -F "images=@image1.jpg" \
  -F "images=@image2.jpg"
```

**Ví dụ với Python requests:**

```python
import requests

files = [
    ('images', open('image1.jpg', 'rb')),
    ('images', open('image2.jpg', 'rb'))
]

response = requests.post(
    'http://localhost:8080/api/trocr/recognize/',
    files=files
)

print(response.json())
```

### 4. YOLO - Detect dấu X

Detect dấu X trong ảnh (x_mark, x_cancelled, hoặc none).

**Request:**

```http
POST /api/yolo/detect/
Content-Type: multipart/form-data

Form data:
- images: [file1.jpg, file2.jpg, ...]
```

**Response:**

```json
{
  "success": true,
  "count": 2,
  "results": [
    {
      "filename": "image1.jpg",
      "label": "x_mark",
      "detections": [
        {
          "class": "x_mark",
          "confidence": 0.95,
          "bbox": [100, 200, 150, 250]
        }
      ],
      "status": "success"
    },
    {
      "filename": "image2.jpg",
      "label": "none",
      "detections": [],
      "status": "success"
    }
  ]
}
```

**Ví dụ với cURL:**

```bash
curl -X POST http://localhost:8080/api/yolo/detect/ \
  -F "images=@checkbox1.jpg" \
  -F "images=@checkbox2.jpg"
```

**Ví dụ với Python requests:**

```python
import requests

files = [
    ('images', open('checkbox1.jpg', 'rb')),
    ('images', open('checkbox2.jpg', 'rb'))
]

response = requests.post(
    'http://localhost:8080/api/yolo/detect/',
    files=files
)

print(response.json())
```

## Labels

### TrOCR

- Trả về text nhận diện được (chuỗi)

### YOLO

- `x_mark`: Có dấu X hợp lệ
- `x_cancelled`: Có dấu X bị gạch bỏ
- `none`: Không có dấu X nào

## Performance Tips

### 1. Batch Processing

Luôn gửi nhiều ảnh cùng lúc thay vì gửi từng ảnh riêng lẻ. API đã được tối ưu để xử lý batch.

❌ **Không tốt:**

```python
for image in images:
    response = requests.post(url, files=[('images', image)])
```

✅ **Tốt:**

```python
files = [('images', open(img, 'rb')) for img in images]
response = requests.post(url, files=files)
```

### 2. Keep-Alive

Sử dụng session để tái sử dụng connection:

```python
import requests

session = requests.Session()

for batch in image_batches:
    files = [('images', open(img, 'rb')) for img in batch]
    response = session.post(url, files=files)
```

### 3. Optimal Batch Size

- TrOCR: 8-16 ảnh/batch
- YOLO: 16-32 ảnh/batch

Tùy vào GPU memory, điều chỉnh batch size cho phù hợp.

### 4. Image Format

- Sử dụng JPEG với chất lượng 85-95%
- Resize ảnh về kích thước phù hợp trước khi gửi (TrOCR: ~384x384, YOLO: ~640x640)

## Error Handling

API trả về status cho từng ảnh. Nếu một ảnh bị lỗi, các ảnh khác vẫn được xử lý bình thường.

```json
{
  "success": true,
  "count": 2,
  "results": [
    {
      "filename": "good.jpg",
      "text": "Nguyen Van A",
      "status": "success"
    },
    {
      "filename": "bad.jpg",
      "text": "",
      "status": "error",
      "error": "Lỗi đọc ảnh: invalid image format"
    }
  ]
}
```

## Monitoring

### Log files

Server log sẽ hiển thị:

- Thời gian load models
- GPU/CPU usage
- Request processing time
- Errors

### Metrics

Thêm middleware để tracking:

- Request count
- Average processing time
- Error rate

## Production Deployment

### 1. Sử dụng Gunicorn

```bash
pip install gunicorn

gunicorn ai_server.wsgi:application \
    --bind 0.0.0.0:8080 \
    --workers 4 \
    --timeout 120 \
    --max-requests 1000
```

### 2. Sử dụng Nginx

Cấu hình Nginx làm reverse proxy:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 100M;
        proxy_read_timeout 120s;
    }
}
```

### 3. Docker

Tạo `Dockerfile`:

```dockerfile
FROM python:3.9

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["gunicorn", "ai_server.wsgi:application", "--bind", "0.0.0.0:8080"]
```

## Troubleshooting

### Models không load được

1. Kiểm tra đường dẫn models
2. Kiểm tra quyền đọc file
3. Xem log khi server khởi động

### Out of memory

1. Giảm batch size
2. Giảm số workers
3. Nâng cấp GPU memory

### Slow processing

1. Kiểm tra GPU có được sử dụng không
2. Tăng batch size
3. Sử dụng mixed precision (FP16)

## License

MIT
