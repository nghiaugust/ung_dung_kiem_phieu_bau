# UDKPB - Ung Dung Kiem Phieu Bau

UDKPB la he thong kiem phieu bau tu dong bang Django va AI server rieng.

## Model AI hien tai

He thong chi su dung 3 model trong `UDKPB/ai_core`:

- `model_vietnameocr`: nhan dien ten ung vien.
- `model_yolo_x`: detect dau X hop le trong cot dong y/khong dong y.
- `model_resnet18_crossed`: detect ten ung vien bi gach trong cau hinh phieu gach ten.

## Cau hinh kiem phieu

- Cau hinh 1: `model_vietnameocr` + `model_yolo_x`.
- Cau hinh 2: ten theo thu tu danh sach ung vien + `model_yolo_x`.
- Cau hinh 3: phieu gach ten 1 cot + `model_resnet18_crossed`.

## Thu muc chinh

- `UDKPB/kiem_phieu_bau`: Django web app.
- `UDKPB/ai_core/ai_server`: AI API server.
- `UDKPB/ai_core/model_vietnameocr`: OCR model.
- `UDKPB/ai_core/model_yolo_x`: YOLO-X weights.
- `UDKPB/ai_core/model_resnet18_crossed`: ResNet18 crossed-name classifier.

## Chay nhanh

```powershell
cd UDKPB
pip install -r requirements.txt

cd kiem_phieu_bau
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

AI server:

```powershell
cd UDKPB/ai_core/ai_server
python run_waitress_ai.py
```

Chi tiet cai dat xem `UDKPB/Setup.md`.
