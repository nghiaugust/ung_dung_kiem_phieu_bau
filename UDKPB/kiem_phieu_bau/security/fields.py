from django.db import models
from django.core.exceptions import ValidationError
from .aes_gcm_encryption import encrypt_aes_gcm, decrypt_aes_gcm

class EncryptedFieldMixin:
    """Mixin chung cho các Encrypted Field"""
    
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        try:
            return decrypt_aes_gcm(value)
        except Exception:
            return f"[ENCRYPTED_DATA_ERROR]" 
    
    def get_prep_value(self, value):
        if value is None:
            return None
        
        # Logic chuẩn: Django object -> DB
        # Chỉ mã hóa nếu value chưa được mã hóa.
        # Nhưng làm sao biết chưa mã hóa?
        # Cách an toàn nhất: Chỉ mã hóa chuỗi Plaintext.
        # Giả định: Người dùng không bao giờ lưu chuỗi bắt đầu bằng 'gAAAA...' (dạng fernet) 
        # hoặc check format base64 (nhưng tốn kém).
        
        # FIX LOGIC: Luôn mã hóa. Tại sao?
        # Vì luồng Django là: Load (decrypt ra plain) -> Edit (plain) -> Save (cần encrypt).
        # Trường hợp duy nhất bị double encrypt là bạn gán thủ công:
        # user.token = "chuỗi_đã_mã_hoá" -> save(). (Trường hợp này rất hiếm).
        
        return encrypt_aes_gcm(str(value))

    def to_python(self, value):
        if value is None:
            return value
        return str(value)

class EncryptedCharField(EncryptedFieldMixin, models.CharField):
    description = "Encrypted CharField"

class EncryptedTextField(EncryptedFieldMixin, models.TextField):
    description = "Encrypted TextField"

# Khuyên dùng: EncryptedEmailField (tự động lower case trước khi encrypt để chuẩn hóa)
class EncryptedEmailField(EncryptedFieldMixin, models.EmailField):
    def get_prep_value(self, value):
        if value:
            value = value.lower() # Chuẩn hóa email
        return super().get_prep_value(value)