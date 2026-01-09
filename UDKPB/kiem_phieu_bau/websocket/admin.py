from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'poll', 'title', 'is_read', 'created_at']
    list_filter = ['is_read', 'created_at']
    search_fields = ['user__username', 'title', 'message']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('user', 'poll')
        }),
        ('Nội dung', {
            'fields': ('title', 'message', 'data')
        }),
        ('Trạng thái', {
            'fields': ('is_read', 'created_at')
        }),
    )
