# WebSocket App - Real-time Notifications

App Django để quản lý WebSocket connections và push notifications cho mobile app trong môi trường mạng nội bộ/offline.

## 📁 Cấu trúc

```
websocket/
├── __init__.py
├── apps.py
├── models.py          # Model Notification
├── admin.py           # Django admin cho Notification
├── consumers.py       # WebSocket consumers
├── routing.py         # WebSocket URL routing
├── utils.py           # Helper functions
├── views.py           # HTTP views (nếu cần)
└── README.md          # File này
```

## 🗄️ Models

### Notification
Lưu trữ thông báo cho users.

**Fields:**
- `user` - Người nhận thông báo
- `poll` - Cuộc bỏ phiếu liên quan (nullable)
- `title` - Tiêu đề
- `message` - Nội dung
- `data` - JSONField chứa dữ liệu bổ sung
- `is_read` - Đã đọc chưa
- `created_at` - Thời gian tạo

**Methods:**
- `mark_as_read()` - Đánh dấu đã đọc
- `to_dict()` - Convert sang dict để gửi qua WebSocket/API

## 🔌 WebSocket Endpoint

### Kết nối
```
ws://server_ip:port/ws/notifications/?token=<access_token>
```

### Authentication
Sử dụng access token trong query string để xác thực.

### Message Format

**Server → Client (Notification):**
```json
{
    "type": "notification",
    "data": {
        "id": 123,
        "poll_id": 1,
        "poll_title": "Bầu ban đại diện",
        "title": "Yêu cầu tham gia mới",
        "message": "user123 muốn tham gia cuộc bỏ phiếu",
        "data": {"member_id": 456},
        "is_read": false,
        "created_at": "2026-01-08T10:00:00"
    }
}
```

**Client → Server (Ping):**
```json
{
    "type": "ping",
    "timestamp": 1234567890
}
```

**Server → Client (Pong):**
```json
{
    "type": "pong",
    "timestamp": 1234567890
}
```

**Client → Server (Mark as Read):**
```json
{
    "type": "mark_read",
    "notification_id": 123
}
```

## 🛠️ Cách sử dụng

### 1. Gửi notification cho 1 user

```python
from websocket.utils import send_notification_to_user

# Gửi thông báo cho user
notification = send_notification_to_user(
    user=target_user,
    poll=poll,
    title='Yêu cầu tham gia được duyệt',
    message=f'Bạn đã được duyệt tham gia {poll.title}',
    data={'member_id': member.member_id}
)
```

### 2. Gửi notification cho managers của poll

```python
from websocket.utils import send_notification_to_poll_managers

# Gửi cho tất cả managers
notifications = send_notification_to_poll_managers(
    poll=poll,
    title='Yêu cầu tham gia mới',
    message=f'{user.username} muốn tham gia cuộc bỏ phiếu',
    data={'member_id': member.member_id}
)
```

### 3. Broadcast cho tất cả members của poll

```python
from websocket.utils import broadcast_to_poll_members

# Broadcast cho tất cả
notifications = broadcast_to_poll_members(
    poll=poll,
    title='Kiểm phiếu hoàn tất',
    message=f'Cuộc bỏ phiếu {poll.title} đã hoàn tất kiểm phiếu',
    data={'total_ballots': 100}
)
```

### 4. Đếm notification chưa đọc

```python
from websocket.utils import get_unread_count

count = get_unread_count(user)
```

### 5. Đánh dấu tất cả đã đọc

```python
from websocket.utils import mark_all_as_read

updated_count = mark_all_as_read(user)
```

## 📝 Ví dụ tích hợp vào API views

### Trong api/views.py - khi có join request

```python
from websocket.utils import send_notification_to_poll_managers

@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_join_poll(request):
    # ... existing code ...
    
    # Tạo PollMember
    member = PollMember.objects.create(
        poll=poll,
        account=user,
        status='pending' if poll.require_approval else 'active',
        role='user'
    )
    
    # Gửi notification cho managers
    if poll.require_approval:
        send_notification_to_poll_managers(
            poll=poll,
            title=f'Yêu cầu tham gia {poll.title}',
            message=f'{user.username} muốn tham gia cuộc bỏ phiếu',
            data={'member_id': member.member_id}
        )
    
    return JsonResponse({...})
```

### Trong api/views.py - khi approve join request

```python
from websocket.utils import send_notification_to_user

@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_approve_join_request(request, poll_id, member_id):
    # ... existing code ...
    
    if action == 'approve':
        member.status = 'active'
        member.save()
        
        # Gửi notification cho user được approve
        send_notification_to_user(
            user=member.account,
            poll=poll,
            title='Yêu cầu tham gia được duyệt',
            message=f'Bạn đã được duyệt tham gia {poll.title}',
            data={'member_id': member.member_id}
        )
    
    return JsonResponse({...})
```

### Trong api/views.py - khi upload ballot

```python
from websocket.utils import send_notification_to_poll_managers

@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_upload_ballot(request, poll_id):
    # ... existing code ...
    
    # Sau khi upload thành công
    send_notification_to_poll_managers(
        poll=poll,
        title='Phiếu bầu mới',
        message=f'{user.username} đã upload phiếu bầu #{ballot.ballot_id}',
        data={'ballot_id': ballot.ballot_id}
    )
    
    return JsonResponse({...})
```

### Trong counting/views.py - khi bắt đầu/hoàn tất counting

```python
from websocket.utils import broadcast_to_poll_members

def start_counting(request, poll_id):
    # ... existing code ...
    
    # Broadcast khi bắt đầu
    broadcast_to_poll_members(
        poll=poll,
        title='Bắt đầu kiểm phiếu',
        message=f'Cuộc bỏ phiếu {poll.title} đã bắt đầu kiểm phiếu',
        data={}
    )
    
    # ... counting logic ...

def complete_counting(request, poll_id):
    # ... existing code ...
    
    # Broadcast khi hoàn tất
    broadcast_to_poll_members(
        poll=poll,
        title='Kiểm phiếu hoàn tất',
        message=f'Cuộc bỏ phiếu {poll.title} đã hoàn tất kiểm phiếu',
        data={'total_ballots': total_ballots}
    )
```

## 🔧 Cấu hình

### settings.py đã được cấu hình:

```python
INSTALLED_APPS = [
    'daphne',  # ASGI server
    ...
    'channels',  # Django Channels
    'websocket',  # App này
    ...
]

ASGI_APPLICATION = 'kiem_phieu_bau.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        # Development: InMemory (không cần Redis)
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
        
        # Production: Redis (uncomment khi deploy)
        # 'BACKEND': 'channels_redis.core.RedisChannelLayer',
        # 'CONFIG': {
        #     "hosts": [('127.0.0.1', 6379)],
        # },
    },
}
```

### asgi.py đã được cấu hình:

WebSocket routing đã được tích hợp vào ASGI application.

## 📦 Dependencies

Thêm vào `requirements.txt`:

```
channels>=4.0.0
daphne>=4.0.0
# channels-redis>=4.1.0  # Uncomment khi dùng Redis cho production
```

## 🚀 Migration

```bash
# Tạo migration cho model Notification
python manage.py makemigrations websocket

# Apply migration
python manage.py migrate websocket
```

## 🧪 Testing

### Test WebSocket connection (Python client)

```python
import asyncio
import websockets
import json

async def test_websocket():
    token = "your_access_token_here"
    uri = f"ws://localhost:8000/ws/notifications/?token={token}"
    
    async with websockets.connect(uri) as websocket:
        # Nhận message kết nối
        response = await websocket.recv()
        print(f"Connected: {response}")
        
        # Gửi ping
        await websocket.send(json.dumps({
            "type": "ping",
            "timestamp": 1234567890
        }))
        
        # Nhận pong
        response = await websocket.recv()
        print(f"Pong: {response}")
        
        # Lắng nghe notifications
        while True:
            message = await websocket.recv()
            print(f"Received: {message}")

asyncio.run(test_websocket())
```

### Test từ browser console

```javascript
const token = "your_access_token_here";
const ws = new WebSocket(`ws://localhost:8000/ws/notifications/?token=${token}`);

ws.onopen = () => {
    console.log('WebSocket connected');
    
    // Send ping
    ws.send(JSON.stringify({
        type: 'ping',
        timestamp: Date.now()
    }));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = () => {
    console.log('WebSocket closed');
};
```

## 🎯 Sử dụng Data Field

Thay vì dùng `notification_type`, bạn có thể lưu thông tin phân loại vào field `data`:

```python
# Ví dụ 1: Join request
send_notification_to_user(
    user=admin,
    poll=poll,
    title='Yêu cầu tham gia',
    message=f'{user.username} muốn tham gia',
    data={
        'action_type': 'join_request',  # Phân loại tùy ý
        'member_id': 123,
        'user_id': 456
    }
)

# Ví dụ 2: Role approved
send_notification_to_user(
    user=member,
    poll=poll,
    title='Nâng cấp quyền',
    message='Bạn đã được nâng cấp lên operator',
    data={
        'action_type': 'role_approved',
        'old_role': 'user',
        'new_role': 'operator'
    }
)
```

## 📚 References

### Android (Kotlin)

```kotlin
import okhttp3.*
import org.json.JSONObject

class WebSocketManager(private val token: String) {
    private var webSocket: WebSocket? = null
    
    fun connect() {
        val client = OkHttpClient()
        val request = Request.Builder()
            .url("ws://server_ip:8000/ws/notifications/?token=$token")
            .build()
        
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                val json = JSONObject(text)
                handleNotification(json)
            }
        })
    }
    
    private fun handleNotification(json: JSONObject) {
        when (json.getString("type")) {
            "notification" -> {
                val data = json.getJSONObject("data")
                showNotification(data)
            }
        }
    }
}
```

### iOS (Swift)

```swift
import Starscream

class WebSocketManager: WebSocketDelegate {
    var socket: WebSocket?
    
    func connect(token: String) {
        var request = URLRequest(url: URL(string: "ws://server_ip:8000/ws/notifications/?token=\(token)")!)
        socket = WebSocket(request: request)
        socket?.delegate = self
        socket?.connect()
    }
    
    func didReceive(event: WebSocketEvent, client: WebSocket) {
        switch event {
        case .text(let string):
            handleMessage(string)
        default:
            break
        }
    }
}
```

## 🔐 Security Notes

- WebSocket authentication qua access token
- Token được validate trước khi accept connection
- Mỗi user chỉ nhận notification của mình
- AllowedHostsOriginValidator đảm bảo CORS security

## 📊 Performance

- InMemoryChannelLayer: tốt cho development, single-server
- Redis ChannelLayer: cần thiết cho production, multiple servers
- Connection timeout: default Django Channels settings
- Reconnection: client phải handle reconnect logic

## 🐛 Troubleshooting

### WebSocket không kết nối được
- Kiểm tra ASGI application đang chạy (daphne/uvicorn)
- Kiểm tra ALLOWED_HOSTS trong settings
- Verify token còn hạn

### Không nhận được notification
- Kiểm tra user đã connect WebSocket chưa
- Kiểm tra channel layer hoạt động (InMemory/Redis)
- Check logs trong consumer

### Channel layer error
- Nếu dùng InMemory: chỉ hoạt động single process
- Nếu dùng Redis: đảm bảo Redis server đang chạy

## 📚 References

- [Django Channels Documentation](https://channels.readthedocs.io/)
- [WebSocket Protocol](https://datatracker.ietf.org/doc/html/rfc6455)
- [Daphne ASGI Server](https://github.com/django/daphne)
