from django.db import models
from django.conf import settings
import secrets


class APIToken(models.Model):
    """
    Token đơn giản cho mobile authentication
    Mỗi user có 1 token duy nhất
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='api_token'
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'api_tokens'
        verbose_name = 'API Token'
        verbose_name_plural = 'API Tokens'

    def __str__(self):
        return f"Token for {self.user.username}"

    @classmethod
    def generate_token(cls):
        """Tạo token ngẫu nhiên 64 ký tự"""
        return secrets.token_urlsafe(48)[:64]

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self.generate_token()
        super().save(*args, **kwargs)
