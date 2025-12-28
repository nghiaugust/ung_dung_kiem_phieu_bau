from django.db import models
from django.conf import settings
import secrets
import hashlib
from security.fields import EncryptedCharField


class APIToken(models.Model):
    """
    Token với Access Token và Refresh Token
    Access Token: thời gian ngắn (1 giờ)
    Refresh Token: thời gian dài (30 ngày)
    
    Tokens được mã hóa AES-256-GCM tự động trong database
    Token Blind Index (hash SHA-256) để hỗ trợ tìm kiếm nhanh
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='api_token'
    )
    # Token được mã hóa AES-256-GCM (không thể tìm kiếm trực tiếp)
    token = EncryptedCharField(max_length=256, db_index=False)
    # Token Blind Index - SHA-256 hash để tìm kiếm (deterministic)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Refresh token được mã hóa AES-256-GCM
    refresh_token = EncryptedCharField(max_length=256, db_index=False, null=True, blank=True)
    # Refresh Token Blind Index - SHA-256 hash để tìm kiếm
    refresh_token_hash = models.CharField(max_length=64, unique=True, db_index=True, null=True, blank=True)
    refresh_token_expires_at = models.DateTimeField(null=True, blank=True)
    
    # Public key của client (dùng cho mã hóa asymmetric)
    public_key = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'api_tokens'
        verbose_name = 'API Token'
        verbose_name_plural = 'API Tokens'

    def __str__(self):
        return f"Token for {self.user.username}"

    @staticmethod
    def hash_token(token: str) -> str:
        """Tạo SHA-256 hash của token cho blind index"""
        if not token:
            return None
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @classmethod
    def generate_token(cls):
        """Tạo token ngẫu nhiên 64 ký tự"""
        return secrets.token_urlsafe(48)[:64]

    def save(self, *args, **kwargs):
        # Tạo token nếu chưa có
        if not self.token:
            self.token = self.generate_token()
        
        # Tự động tạo hash cho token (để tìm kiếm)
        if self.token and not self.token_hash:
            self.token_hash = self.hash_token(self.token)
        
        # Tự động tạo hash cho refresh_token (nếu có)
        if self.refresh_token and not self.refresh_token_hash:
            self.refresh_token_hash = self.hash_token(self.refresh_token)
        
        super().save(*args, **kwargs)
    
    @classmethod
    def get_by_token(cls, plaintext_token: str):
        """
        Tìm APIToken bằng plaintext token (dùng blind index)
        
        Args:
            plaintext_token: Token plaintext từ client
            
        Returns:
            APIToken instance hoặc None
        """
        if not plaintext_token:
            return None
        
        token_hash = cls.hash_token(plaintext_token)
        try:
            return cls.objects.select_related('user').get(
                token_hash=token_hash,
                is_active=True
            )
        except cls.DoesNotExist:
            return None
    
    @classmethod
    def get_by_refresh_token(cls, plaintext_refresh_token: str):
        """
        Tìm APIToken bằng plaintext refresh token (dùng blind index)
        
        Args:
            plaintext_refresh_token: Refresh token plaintext từ client
            
        Returns:
            APIToken instance hoặc None
        """
        if not plaintext_refresh_token:
            return None
        
        refresh_token_hash = cls.hash_token(plaintext_refresh_token)
        try:
            return cls.objects.select_related('user').get(
                refresh_token_hash=refresh_token_hash,
                is_active=True
            )
        except cls.DoesNotExist:
            return None
