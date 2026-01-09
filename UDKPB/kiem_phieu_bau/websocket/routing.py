"""
WebSocket Routing
Định nghĩa URL patterns cho WebSocket connections
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # WebSocket endpoint cho notifications
    # ws://localhost:8000/ws/notifications/?token=<access_token>
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
]
