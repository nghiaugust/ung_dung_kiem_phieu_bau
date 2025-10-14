# Ứng Dụng Kiểm Phiếu Bầu (UDKPB)

## Giới thiệu

UDKPB là hệ thống kiểm phiếu bầu tự động, ứng dụng công nghệ nhận dạng ký tự quang học (OCR) và học máy, giúp tăng tốc, giảm sai sót và minh bạch hóa quá trình kiểm phiếu. Hệ thống hiện tại sử dụng phương pháp **kết hợp TrOCR + YOLO** để nhận diện, phân tích và xác thực phiếu bầu một cách tối ưu. Phát triển bởi nhóm sinh viên Học viện Kỹ thuật Mật mã.

## Tính năng nổi bật

- Xử lý phiếu bầu bằng mô hình **TrOCR** (transformers của Microsoft) kết hợp **YOLO** để nhận diện tên ứng viên và dấu X trên phiếu.
- Tự động phân tích, đánh giá độ chính xác nhận dạng (CER/WER, Precision/Recall).
- Quản lý, lưu trữ kết quả kiểm phiếu, hỗ trợ hậu kiểm và chỉnh sửa kết quả.
- Giao diện web quản lý phiếu bầu, tài khoản, cuộc bỏ phiếu, ứng viên, thống kê kết quả.
- Quản lý tài khoản, phân quyền (admin, assistant, user).
- Tải mẫu phiếu, upload phiếu, hậu kiểm, thống kê chi tiết từng cuộc bỏ phiếu.

## Quy trình kiểm phiếu kết hợp (TrOCR + YOLO)

1. **Tiền xử lý & cắt ảnh**: Tự động phát hiện layout phiếu, cắt thành các vùng (STT, họ tên, ô đồng ý/không đồng ý).
2. **Nhận diện tên ứng viên**: Sử dụng TrOCR để đọc tên từ vùng ảnh tương ứng.
3. **Nhận diện dấu X**: Sử dụng YOLO để phát hiện dấu X hợp lệ và dấu X bị gạch bỏ ở các ô chọn.
4. **Tổng hợp kết quả**: Đánh giá phiếu hợp lệ/lỗi, thống kê số lượt đồng ý cho từng ứng viên.
5. **Lưu kết quả**: Kết quả được lưu dưới dạng JSON, phục vụ thống kê, hậu kiểm và xuất báo cáo.

## Kiến trúc dự án

- **UDKPB/ballot_processing_system/processors/trocr_yolo.py**: Bộ xử lý phiếu bầu kết hợp TrOCR + YOLO (mặc định và duy nhất khi chạy hệ thống).
- **UDKPB/ballot_processing_system/core/**: Tiền xử lý ảnh, nhận diện ký tự, hỗ trợ các thuật toán.
- **UDKPB/ballot_processing_system/models/**: Lưu trữ mô hình YOLO.
- **UDKPB/ballot_processing_system/models_trocr/**: Lưu trữ mô hình TrOCR.
- **UDKPB/kiem_phieu_bau/**: Web app Django quản lý phiếu bầu, tài khoản, cuộc bỏ phiếu, media, templates giao diện.
- **UDKPB/kiem_phieu_bau/static/**: Tài nguyên tĩnh (ảnh mẫu, CSS, JS, logo).

## Công nghệ sử dụng

- Python >= 3.8
- Django
- Transformers (TrOCR)
- YOLO (Ultralytics)
- MySQL
- HTML/CSS/JS

## Hướng dẫn cài đặt & sử dụng

Vui lòng xem chi tiết tại [UDKPB/Setup.md](UDKPB/Setup.md)

Tóm tắt các bước chính:

1. Chuẩn bị môi trường Python, pip, virtualenv
2. Cài đặt các thư viện từ `requirements.txt`
3. Tải mô hình TrOCR
4. Cấu hình file `.env` và `settings.py` cho Django
5. Khởi tạo database và migrate
6. Collect static files
7. Tạo tài khoản admin
8. Chạy server

## Giao diện & chức năng web

- Trang chủ, đăng nhập/đăng ký, quản lý tài khoản
- Tạo cuộc bỏ phiếu, thêm/sửa/xóa ứng viên
- Upload phiếu bầu, xem danh sách phiếu, chi tiết từng phiếu
- Thống kê kết quả, hậu kiểm phiếu, xuất báo cáo
- Tải mẫu phiếu bầu ZIP

## Đóng góp & phát triển

- Đóng góp mã nguồn qua pull request
- Báo lỗi hoặc đề xuất tính năng qua Issues
- Liên hệ: domanhnghiaforwork@gmail.com

## License

Dự án sử dụng mã nguồn mở, vui lòng tham khảo file LICENSE để biết chi tiết.

---

**Lưu ý:**

- Hệ thống hiện chỉ hỗ trợ kiểm phiếu kết hợp TrOCR + YOLO (không hỗ trợ các phương pháp khác).
- Đảm bảo cấu hình đúng thông tin kết nối MySQL.
- Nếu gặp lỗi cài đặt `mysqlclient`, có thể thay bằng `pymysql`.
- Đảm bảo mở port 8000 hoặc cấu hình reverse proxy khi deploy.
