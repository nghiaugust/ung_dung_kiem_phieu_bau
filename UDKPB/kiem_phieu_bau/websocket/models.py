from django.db import models
from django.conf import settings


class Notification(models.Model):
    """
    Model thông báo cho user
    Dùng cho WebSocket push notifications và polling API
    """
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text='Người nhận thông báo'
    )
    poll = models.ForeignKey(
        'poll.Poll',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        help_text='Cuộc bỏ phiếu liên quan'
    )
    title = models.CharField(
        max_length=255,
        help_text='Tiêu đề thông báo'
    )
    message = models.TextField(
        help_text='Nội dung thông báo'
    )
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Dữ liệu bổ sung (member_id, ballot_id, etc.)'
    )
    is_read = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Đã đọc chưa'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text='Thời gian tạo'
    )
    
    class Meta:
        db_table = 'notifications'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} for {self.user.username} at {self.created_at}"
    
    def mark_as_read(self):
        """Đánh dấu đã đọc"""
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])
    
    def to_dict(self):
        """Convert sang dict để gửi qua WebSocket/API"""
        return {
            'id': self.id,
            'poll_id': self.poll_id,
            'poll_title': self.poll.title if self.poll else None,
            'title': self.title,
            'message': self.message,
            'data': self.data,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat()
        }
