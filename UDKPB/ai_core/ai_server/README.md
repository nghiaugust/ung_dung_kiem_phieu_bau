# AI Server - Waitress Configuration

# Chạy server
python run_waitress_ai.py
```

Hoặc double-click: `start_ai_server.bat`

## 🎯 Cấu hình tối ưu

- **1 Process**: Model AI chỉ load 1 lần → Tiết kiệm RAM
- **4 Threads**: Xử lý 4 requests đồng thời → Không bị treo
- **Port**: 8080
- **Timeout**: 300s (cho AI processing)

## 📡 Endpoints

- Health: `http://localhost:8080/api/health/`
- Info: `http://localhost:8080/api/info/`
- TrOCR: `POST http://localhost:8080/api/trocr/recognize/`
- YOLO: `POST http://localhost:8080/api/yolo/detect/`

```
