import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

class AESGCMEncryption:
    _instance = None
    _cipher = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        # Ưu tiên lấy từ os.environ để an toàn
        encryption_key = os.environ.get('ENCRYPTION_KEY')
        
        if not encryption_key:
            # Fallback nếu muốn để trong settings.py (tuỳ chọn)
            from django.conf import settings
            encryption_key = getattr(settings, 'ENCRYPTION_KEY', None)

        if not encryption_key:
            raise ValueError("Chưa cấu hình ENCRYPTION_KEY (Hex 32 bytes)")
        
        try:
            key_bytes = bytes.fromhex(encryption_key)
            if len(key_bytes) != 32:
                raise ValueError("ENCRYPTION_KEY phải là 32 bytes (64 ký tự hex)")
            self._cipher = AESGCM(key_bytes)
        except Exception as e:
            raise ValueError(f"Lỗi Key: {e}")
    
    def encrypt(self, plaintext: str) -> str:
        if plaintext is None: return None
        # Convert sang string nếu lỡ truyền vào số/object
        if not isinstance(plaintext, str):
            plaintext = str(plaintext)
            
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, plaintext.encode('utf-8'), None)
        return base64.b64encode(nonce + ciphertext).decode('utf-8')
    
    def decrypt(self, encrypted_text: str) -> str:
        if not encrypted_text: return None
        try:
            encrypted_data = base64.b64decode(encrypted_text)
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]
            return self._cipher.decrypt(nonce, ciphertext, None).decode('utf-8')
        except (ValueError, InvalidTag,  Exception) as e:
            # Log lỗi ở đây nếu cần (dùng logging module)
            raise ValueError(f"Decryption failed: {str(e)}")

# Singleton Accessors
def get_encryptor():
    global _aes_gcm_encryptor
    # Lazy loading: Chỉ khởi tạo khi thực sự cần dùng
    return AESGCMEncryption()

def encrypt_aes_gcm(data):
    return get_encryptor().encrypt(data)

def decrypt_aes_gcm(data):
    return get_encryptor().decrypt(data)