# AI Server

Run:

```powershell
python run_waitress_ai.py
```

The server loads these models once in a single process:

- `model_vietnameocr`
- `model_resnet18_x`
- `model_resnet18_crossed`

Endpoints:

- Health: `GET http://localhost:8081/api/health/`
- Info: `GET http://localhost:8081/api/info/`
- VietNameOCR: `POST http://localhost:8081/api/model_vietnameocr/recognize/`
- ResNet18-X: `POST http://localhost:8081/api/model_resnet18_x/detect/`
- ResNet18 crossed: `POST http://localhost:8081/api/model_resnet18_crossed/detect/`
