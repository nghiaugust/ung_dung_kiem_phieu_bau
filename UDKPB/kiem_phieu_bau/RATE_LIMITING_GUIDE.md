# Hướng dẫn cấu hình Rate Limiting cho hệ thống

## Tổng quan

Hệ thống đã được cấu hình với middleware Rate Limiting để bảo vệ server khỏi các cuộc tấn công DDoS và giới hạn số lượng requests từ mỗi client.

## Các tính năng

### 1. RateLimitMiddleware (IP-based)
- Giới hạn số lượng requests dựa trên địa chỉ IP
- Áp dụng cho tất cả requests đến server
- Hỗ trợ whitelist IPs
- Hỗ trợ exempt paths (các đường dẫn được miễn giới hạn)

### 2. UserBasedRateLimitMiddleware (User-based)
- Giới hạn khác nhau cho user đã đăng nhập và chưa đăng nhập
- User đã đăng nhập có giới hạn cao hơn
- User chưa đăng nhập giới hạn theo IP

## Cấu hình

### Tệp .env
```env
# Bật/tắt rate limiting
RATE_LIMIT_ENABLED=True

# IP-based rate limiting
RATE_LIMIT_REQUESTS=100          # Số requests tối đa
RATE_LIMIT_PERIOD=60             # Thời gian (giây)

# User-based rate limiting
RATE_LIMIT_AUTHENTICATED_REQUESTS=200    # User đã đăng nhập
RATE_LIMIT_ANONYMOUS_REQUESTS=50         # User chưa đăng nhập
```

### Tệp settings.py

Middleware đã được thêm vào `MIDDLEWARE`:
```python
MIDDLEWARE = [
    ...
    'kiem_phieu_bau.rate_limiting_middleware.RateLimitMiddleware',  # Global rate limiting
    # 'kiem_phieu_bau.rate_limiting_middleware.UserBasedRateLimitMiddleware',  # Alternative
]
```

**Lưu ý:** Chỉ nên sử dụng một trong hai middleware. Bỏ comment middleware bạn muốn sử dụng.

### Whitelist IPs
Thêm IPs cần miễn giới hạn trong `settings.py`:
```python
RATE_LIMIT_WHITELIST_IPS = [
    '127.0.0.1',
    'localhost',
    '192.168.1.100',  # Thêm IP server nội bộ
]
```

### Exempt Paths
Thêm paths cần miễn giới hạn:
```python
RATE_LIMIT_EXEMPT_PATHS = [
    '/static/',
    '/media/',
    '/admin/jsi18n/',
    '/health-check/',  # Health check endpoint
]
```

## Response Headers

Mỗi response sẽ có các headers sau:
- `X-RateLimit-Limit`: Giới hạn tối đa
- `X-RateLimit-Remaining`: Số requests còn lại
- `X-RateLimit-Reset`: Thời gian reset (Unix timestamp)

## Response khi vượt giới hạn

### JSON Response (cho AJAX/API)
```json
{
    "error": "Rate limit exceeded",
    "message": "Bạn đã vượt quá giới hạn 100 requests trong 60 giây.",
    "retry_after": 45
}
```
HTTP Status: `429 Too Many Requests`

### HTML Response
```html
<h1>429 Too Many Requests</h1>
<p>Bạn đã vượt quá giới hạn 100 requests trong 60 giây.</p>
<p>Vui lòng thử lại sau 45 giây.</p>
```

## Cache Backend

Mặc định sử dụng `LocMemCache` (trong memory). Cho production nên sử dụng Redis:

### Cài đặt Redis
```bash
pip install redis django-redis
```

### Cấu hình Redis trong settings.py
```python
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    },
}
```

## Kiểm tra hoạt động

### Test với curl
```bash
# Gửi nhiều requests liên tiếp
for i in {1..10}; do
  curl -I http://localhost:8000/
done
```

### Test với Python
```python
import requests
import time

url = 'http://localhost:8000/'
for i in range(120):
    response = requests.get(url)
    print(f"Request {i+1}: Status {response.status_code}")
    if response.status_code == 429:
        print(f"Rate limited! Retry after: {response.headers.get('Retry-After')} seconds")
        break
    time.sleep(0.5)
```

## Tùy chỉnh cho các endpoint cụ thể

Nếu muốn tùy chỉnh rate limit cho các endpoint cụ thể, có thể tạo decorator:

```python
# kiem_phieu_bau/rate_limiting_decorator.py
from functools import wraps
from django.http import JsonResponse
from django.core.cache import cache
import time

def custom_rate_limit(max_requests=50, period=60):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Lấy IP
            ip = request.META.get('REMOTE_ADDR')
            cache_key = f'custom_rate_limit_{view_func.__name__}_{ip}'
            
            request_data = cache.get(cache_key, {'count': 0, 'reset_time': time.time() + period})
            current_time = time.time()
            
            if current_time >= request_data['reset_time']:
                request_data = {'count': 1, 'reset_time': current_time + period}
            else:
                request_data['count'] += 1
            
            cache.set(cache_key, request_data, period)
            
            if request_data['count'] > max_requests:
                return JsonResponse({
                    'error': 'Rate limit exceeded',
                    'message': f'Vượt quá {max_requests} requests trong {period} giây'
                }, status=429)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
```

### Sử dụng decorator
```python
from kiem_phieu_bau.rate_limiting_decorator import custom_rate_limit

@custom_rate_limit(max_requests=10, period=60)
def sensitive_view(request):
    # View logic here
    pass
```

## Monitoring

Để theo dõi rate limiting, có thể thêm logging:

```python
import logging
logger = logging.getLogger(__name__)

# Trong middleware
if request_data['count'] > rate_limit:
    logger.warning(f'Rate limit exceeded for IP {ip_address}: {request_data["count"]} requests')
```

## Best Practices

1. **Production:** Sử dụng Redis thay vì LocMemCache
2. **API endpoints:** Giới hạn thấp hơn (10-50 requests/phút)
3. **Static files:** Thêm vào exempt paths
4. **Health check:** Thêm vào exempt paths
5. **Load balancer:** Đảm bảo IP forwarding đúng với `X-Forwarded-For` header
6. **Monitor:** Theo dõi logs để điều chỉnh giới hạn phù hợp

## Troubleshooting

### Vấn đề: Rate limit không hoạt động
- Kiểm tra `RATE_LIMIT_ENABLED=True` trong .env
- Kiểm tra middleware đã được thêm vào `MIDDLEWARE` trong settings.py
- Kiểm tra cache backend đang hoạt động

### Vấn đề: Bị rate limit quá nhanh
- Tăng `RATE_LIMIT_REQUESTS` hoặc `RATE_LIMIT_PERIOD`
- Thêm IP vào whitelist nếu cần
- Kiểm tra có nhiều requests không cần thiết không

### Vấn đề: IP không đúng (behind proxy/load balancer)
- Đảm bảo proxy forward `X-Forwarded-For` header
- Middleware đã xử lý `X-Forwarded-For` tự động
