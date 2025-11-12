from django.contrib import admin
from .models import APIToken


@admin.register(APIToken)
class APITokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'token_preview', 'created_at', 'last_used', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__username', 'token']
    readonly_fields = ['token', 'created_at', 'last_used']
    
    def token_preview(self, obj):
        """Hiển thị 8 ký tự đầu của token"""
        return f"{obj.token[:8]}..." if obj.token else ""
    token_preview.short_description = 'Token'
