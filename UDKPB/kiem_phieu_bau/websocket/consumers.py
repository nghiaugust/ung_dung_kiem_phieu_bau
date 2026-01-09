"""
WebSocket Consumers
Xử lý WebSocket connections và push notifications
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from api.models import APIToken

User = get_user_model()


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Consumer cho real-time notifications
    
    WebSocket URL: ws://server/ws/notifications/?token=<access_token>
    
    Messages từ server:
    {
        "type": "notification",
        "data": {
            "id": 123,
            "type": "join_request",
            "poll_id": 1,
            "title": "...",
            "message": "...",
            "data": {...},
            "created_at": "2026-01-08T10:00:00"
        }
    }
    """
    
    async def connect(self):
        """Khi client kết nối WebSocket"""
        # Lấy token từ query string
        query_string = self.scope.get('query_string', b'').decode('utf-8')
        token = None
        
        # Parse query string để lấy token
        for param in query_string.split('&'):
            if param.startswith('token='):
                token = param.split('=')[1]
                break
        
        # Xác thực token
        if not token:
            await self.close(code=4001)  # Unauthorized
            return
        
        user = await self.get_user_from_token(token)
        if not user:
            await self.close(code=4001)  # Unauthorized
            return
        
        # Lưu user vào scope
        self.user = user
        self.user_group_name = f"user_{user.id}"
        
        # Join user-specific group
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        # Accept connection
        await self.accept()
        
        # Gửi message xác nhận kết nối
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': f'Connected as {user.username}',
            'user_id': user.id
        }))
    
    async def disconnect(self, close_code):
        """Khi client ngắt kết nối"""
        if hasattr(self, 'user_group_name'):
            # Leave user group
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """
        Nhận message từ client (nếu cần)
        Client có thể gửi ping để keep-alive
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type', '')
            
            if message_type == 'ping':
                # Respond to ping
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                }))
            elif message_type == 'mark_read':
                # Đánh dấu notification đã đọc
                notification_id = data.get('notification_id')
                if notification_id:
                    await self.mark_notification_read(notification_id)
                    await self.send(text_data=json.dumps({
                        'type': 'notification_marked_read',
                        'notification_id': notification_id
                    }))
        except json.JSONDecodeError:
            pass
    
    async def notification_message(self, event):
        """
        Handler cho notification message từ channel layer
        Được gọi khi có ai đó send message tới group này
        """
        # Gửi notification tới WebSocket
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'data': event['data']
        }))
    
    async def broadcast_message(self, event):
        """
        Handler cho broadcast message (gửi tới tất cả users trong poll)
        """
        await self.send(text_data=json.dumps({
            'type': 'broadcast',
            'data': event['data']
        }))
    
    @database_sync_to_async
    def get_user_from_token(self, token):
        """Lấy user từ access token"""
        try:
            api_token = APIToken.get_by_token(token)
            if api_token and api_token.is_active:
                return api_token.user
        except Exception:
            pass
        return None
    
    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        """Đánh dấu notification đã đọc"""
        from .models import Notification
        try:
            notification = Notification.objects.get(
                id=notification_id,
                user=self.user
            )
            notification.mark_as_read()
        except Notification.DoesNotExist:
            pass
