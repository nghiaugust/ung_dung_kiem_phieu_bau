# AI Server - Waitress Configuration

## Run

```bash
python run_waitress_ai.py
```

## Endpoints

- Health: `GET http://localhost:8081/api/health/`
- Info: `GET http://localhost:8081/api/info/`
- VietNameOCR: `POST http://localhost:8081/api/vietnameocr/recognize/`
- YOLO: `POST http://localhost:8081/api/yolo/detect/`
