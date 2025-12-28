"""
Rate Limiting Middleware cho toàn bộ hệ thống
Giới hạn số lượng requests từ mỗi IP trong một khoảng thời gian
"""
import time
import os
from django.core.cache import cache
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.template import Template, Context


class RateLimitMiddleware:
    """
    Middleware áp dụng rate limiting global cho tất cả requests
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Lấy cấu hình từ settings, nếu không có thì dùng giá trị mặc định
        self.rate_limit = getattr(settings, 'RATE_LIMIT_REQUESTS', 100)  # Số requests tối đa
        self.rate_period = getattr(settings, 'RATE_LIMIT_PERIOD', 60)  # Thời gian (giây)
        self.rate_enabled = getattr(settings, 'RATE_LIMIT_ENABLED', True)  # Bật/tắt rate limiting
        self.whitelist_ips = getattr(settings, 'RATE_LIMIT_WHITELIST_IPS', ['127.0.0.1'])  # IPs được miễn
        self.exempt_paths = getattr(settings, 'RATE_LIMIT_EXEMPT_PATHS', [])  # Paths được miễn
    
    def __call__(self, request):
        # Nếu rate limiting bị tắt, bỏ qua
        if not self.rate_enabled:
            return self.get_response(request)
        
        # Lấy IP của client
        ip_address = self.get_client_ip(request)
        
        # Kiểm tra whitelist
        if ip_address in self.whitelist_ips:
            return self.get_response(request)
        
        # Kiểm tra exempt paths
        request_path = request.path
        for exempt_path in self.exempt_paths:
            if request_path.startswith(exempt_path):
                return self.get_response(request)
        
        # Tạo cache key dựa trên IP
        cache_key = f'rate_limit_{ip_address}'
        
        # Lấy thông tin từ cache
        request_data = cache.get(cache_key, {'count': 0, 'reset_time': time.time() + self.rate_period})
        
        current_time = time.time()
        
        # Nếu đã hết thời gian rate limit, reset counter
        if current_time >= request_data['reset_time']:
            request_data = {
                'count': 1,
                'reset_time': current_time + self.rate_period
            }
        else:
            # Tăng counter
            request_data['count'] += 1
        
        # Lưu vào cache
        cache.set(cache_key, request_data, self.rate_period)
        
        # Kiểm tra có vượt quá giới hạn không
        if request_data['count'] > self.rate_limit:
            retry_after = int(request_data['reset_time'] - current_time)
            
            # Nếu là AJAX request hoặc API, trả về JSON
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                return JsonResponse({
                    'error': 'Rate limit exceeded',
                    'message': f'Bạn đã vượt quá giới hạn {self.rate_limit} requests trong {self.rate_period} giây.',
                    'retry_after': retry_after
                }, status=429)
            
            # Trả về HTML response từ template
            html_content = self.render_rate_limit_template(
                self.rate_limit, 
                self.rate_period, 
                retry_after
            )
            response = HttpResponse(html_content, status=429)
            response['Retry-After'] = str(retry_after)
            return response
        
        # Thêm rate limit headers vào response
        response = self.get_response(request)
        response['X-RateLimit-Limit'] = str(self.rate_limit)
        response['X-RateLimit-Remaining'] = str(max(0, self.rate_limit - request_data['count']))
        response['X-RateLimit-Reset'] = str(int(request_data['reset_time']))
        
        return response
    
    def get_client_ip(self, request):
        """
        Lấy địa chỉ IP thực của client (xử lý cả proxy/load balancer)
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def render_rate_limit_template(self, rate_limit, rate_period, retry_after):
        """
        Load và render template HTML cho trang 429
        """
        try:
            template_path = os.path.join(
                settings.BASE_DIR,
                'kiem_phieu_bau',
                'templates',
                'rate_limit_429.html'
            )
            
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
            template = Template(template_content)
            context = Context({
                'rate_limit': rate_limit,
                'rate_period': rate_period,
                'retry_after': retry_after
            })
            
            return template.render(context)
        except Exception as e:
            # Fallback nếu không load được template
            return f'''
                <h1>429 Too Many Requests</h1>
                <p>Bạn đã vượt quá giới hạn {rate_limit} requests trong {rate_period} giây.</p>
                <p>Vui lòng thử lại sau {retry_after} giây.</p>
            '''


class UserBasedRateLimitMiddleware:
    """
    Middleware rate limiting dựa trên user (cho user đã đăng nhập)
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.rate_limit_authenticated = getattr(settings, 'RATE_LIMIT_AUTHENTICATED_REQUESTS', 200)
        self.rate_limit_anonymous = getattr(settings, 'RATE_LIMIT_ANONYMOUS_REQUESTS', 50)
        self.rate_period = getattr(settings, 'RATE_LIMIT_PERIOD', 60)
        self.rate_enabled = getattr(settings, 'RATE_LIMIT_ENABLED', True)
    
    def __call__(self, request):
        if not self.rate_enabled:
            return self.get_response(request)
        
        # Xác định rate limit dựa trên trạng thái đăng nhập
        if request.user.is_authenticated:
            rate_limit = self.rate_limit_authenticated
            cache_key = f'rate_limit_user_{request.user.id}'
        else:
            rate_limit = self.rate_limit_anonymous
            ip_address = self.get_client_ip(request)
            cache_key = f'rate_limit_anon_{ip_address}'
        
        # Lấy thông tin từ cache
        request_data = cache.get(cache_key, {'count': 0, 'reset_time': time.time() + self.rate_period})
        
        current_time = time.time()
        
        # Reset nếu hết thời gian
        if current_time >= request_data['reset_time']:
            request_data = {
                'count': 1,
                'reset_time': current_time + self.rate_period
            }
        else:
            request_data['count'] += 1
        
        # Lưu vào cache
        cache.set(cache_key, request_data, self.rate_period)
        
        # Kiểm tra giới hạn
        if request_data['count'] > rate_limit:
            retry_after = int(request_data['reset_time'] - current_time)
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                return JsonResponse({
                    'error': 'Rate limit exceeded',
                    'message': f'Bạn đã vượt quá giới hạn {rate_limit} requests trong {self.rate_period} giây.',
                    'retry_after': retry_after
                }, status=429)
            
            # Trả về HTML response từ template
            html_content = self.render_rate_limit_template(
                rate_limit, 
                self.rate_period, 
                retry_after
            )
            response = HttpResponse(html_content, status=429)
            response['Retry-After'] = str(retry_after)
            return response
        
        # Thêm headers
        response = self.get_response(request)
        response['X-RateLimit-Limit'] = str(rate_limit)
        response['X-RateLimit-Remaining'] = str(max(0, rate_limit - request_data['count']))
        response['X-RateLimit-Reset'] = str(int(request_data['reset_time']))
        
        return response
    
    def get_client_ip(self, request):
        """Lấy địa chỉ IP của client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def render_rate_limit_template(self, rate_limit, rate_period, retry_after):
        """
        Load và render template HTML cho trang 429
        """
        try:
            template_path = os.path.join(
                settings.BASE_DIR,
                'kiem_phieu_bau',
                'templates',
                'rate_limit_429.html'
            )
            
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
            template = Template(template_content)
            context = Context({
                'rate_limit': rate_limit,
                'rate_period': rate_period,
                'retry_after': retry_after
            })
            
            return template.render(context)
        except Exception as e:
            # Fallback nếu không load được template
            return f'''
                <h1>429 Too Many Requests</h1>
                <p>Bạn đã vượt quá giới hạn {rate_limit} requests trong {rate_period} giây.</p>
                <p>Vui lòng thử lại sau {retry_after} giây.</p>
            '''

