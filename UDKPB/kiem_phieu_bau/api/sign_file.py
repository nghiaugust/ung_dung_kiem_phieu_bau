import base64
import os
import sys
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

def sign_image_file(image_path, private_key_path="private_key.pem"):
    # 1. Kiểm tra file tồn tại
    if not os.path.exists(image_path):
        print(f"❌ Lỗi: Không tìm thấy file ảnh tại '{image_path}'")
        return
    if not os.path.exists(private_key_path):
        print(f"❌ Lỗi: Không tìm thấy private key tại '{private_key_path}'. Hãy chạy gen_keys.py trước.")
        return

    try:
        # 2. Đọc Private Key từ file
        with open(private_key_path, "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend()
            )

        # 3. Đọc dữ liệu ảnh (Binary)
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()

        # 4. Ký số (Sử dụng PSS và SHA256 - Bắt buộc để khớp với server)
        signature = private_key.sign(
            image_data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )

        # 5. Encode sang Base64
        signature_base64 = base64.b64encode(signature).decode('utf-8')
        
        print("\n" + "="*50)
        print(f"FILE: {os.path.basename(image_path)}")
        print("="*50)
        print("CHỮ KÝ SỐ (Copy dòng dưới vào JSON 'signatures'):\n")
        print(signature_base64)
        print("\n" + "="*50)

    except Exception as e:
        print(f"❌ Có lỗi xảy ra: {str(e)}")

if __name__ == "__main__":
    # Cách dùng: Chạy file và nhập đường dẫn, hoặc truyền tham số dòng lệnh
    if len(sys.argv) > 1:
        img_path = sys.argv[1]
    else:
        # Tự động tạo file test nếu chưa có để bạn test luôn
        if not os.path.exists("test_image.jpg"):
            with open("test_image.jpg", "wb") as f:
                f.write(b"Day la file anh gia lap de test chu ky so")
            print("⚠️ Đã tạo file giả lập 'test_image.jpg' để test.")
            img_path = "test_image.jpg"
        else:
            img_path = input("Nhập đường dẫn file ảnh cần ký: ").strip().strip('"')

    sign_image_file(img_path)