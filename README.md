# Ứng Dụng Kiểm Phiếu Bầu (UDKPB)

UDKPB là hệ thống kiểm phiếu bầu tự động dùng OCR và YOLO để hỗ trợ nhận diện tên ứng viên, phát hiện dấu X trên phiếu, tổng hợp kết quả và phục vụ hậu kiểm.

## Mô hình AI

- **VietNameOCR**: nhận diện tên ứng viên từ vùng ảnh họ tên.
- **YOLO**: phát hiện dấu X hợp lệ hoặc dấu X bị gạch bỏ trong các ô chọn.

## Quy Trình Kiểm Phiếu

1. Tiền xử lý phiếu và cắt ảnh thành các ô theo bảng.
2. Dùng VietNameOCR để đọc tên ứng viên ở cấu hình 1.
3. Dùng YOLO để nhận diện ô đồng ý/không đồng ý.
4. Ghép kết quả OCR và YOLO để xác định lựa chọn hợp lệ.
5. Lưu kết quả để thống kê, hậu kiểm và xuất báo cáo.

## Cấu Trúc Chính

- `UDKPB/ai_core/ai_server/`: AI API server cho VietNameOCR và YOLO.
- `UDKPB/ai_core/model_vietnameocr/`: mã nguồn và cấu hình VietNameOCR.
- `UDKPB/ai_core/model_yolo_x/`: weights YOLO.
- `UDKPB/kiem_phieu_bau/`: web app Django quản lý cuộc bỏ phiếu, phiếu bầu, kiểm phiếu và hậu kiểm.

## Công Nghệ

- Python, Django, Celery
- PyTorch, VietNameOCR
- YOLO Ultralytics
- MySQL
- HTML/CSS/JS

## Cài Đặt

Xem hướng dẫn chi tiết tại [UDKPB/Setup.md](UDKPB/Setup.md).

Lưu ý: hệ thống hiện có 2 cấu hình kiểm phiếu: chỉ YOLO, hoặc VietNameOCR + YOLO.
