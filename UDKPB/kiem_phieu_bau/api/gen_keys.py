import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

def generate_and_save_keys():
    print("--- ĐANG SINH CẶP KHÓA RSA 2048-BIT ---")
    
    # 1. Sinh khóa
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # 2. Xuất và lưu Private Key (private_key.pem)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    with open("private_key.pem", "wb") as f:
        f.write(private_pem)
    print("✅ Đã lưu: private_key.pem (Giữ bí mật file này!)")

    # 3. Xuất và lưu Public Key (public_key.pem)
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    with open("public_key.pem", "wb") as f:
        f.write(public_pem)
    print("✅ Đã lưu: public_key.pem (Gửi nội dung file này lên Server)")

if __name__ == "__main__":
    generate_and_save_keys()