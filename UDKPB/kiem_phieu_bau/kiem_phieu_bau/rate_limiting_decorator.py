"""
Decorator để áp dụng rate limiting cho các view cụ thể
"""
import time
import os
from functools import wraps
from django.core.cache import cache
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.template import Template, Context


def rate_limit(max_requests=10, period=60, key_prefix='custom'):
    """
    Decorator để giới hạn số lượng requests cho một view cụ thể
    
    Args:
        max_requests: Số requests tối đa
        period: Thời gian tính bằng giây
        key_prefix: Prefix cho cache key để phân biệt các endpoint
    
    Usage:
        @rate_limit(max_requests=10, period=60, key_prefix='login')
        def login_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Lấy IP của client
            ip_address = get_client_ip(request)
            
            # Tạo cache key duy nhất cho view này
            cache_key = f'rate_limit_{key_prefix}_{ip_address}'
            
            # Lấy thông tin từ cache
            request_data = cache.get(cache_key, {
                'count': 0, 
                'reset_time': time.time() + period
            })
            
            current_time = time.time()
            
            # Reset nếu hết thời gian
            if current_time >= request_data['reset_time']:
                request_data = {
                    'count': 1,
                    'reset_time': current_time + period
                }
            else:
                request_data['count'] += 1
            
            # Lưu vào cache
            cache.set(cache_key, request_data, period)
            
            # Kiểm tra giới hạn
            if request_data['count'] > max_requests:
                retry_after = int(request_data['reset_time'] - current_time)
                
                # Kiểm tra nếu là API request hoặc AJAX request
                is_api = (
                    request.path.startswith('/api/') or 
                    request.headers.get('x-requested-with') == 'XMLHttpRequest' or
                    request.headers.get('Accept', '').find('application/json') != -1 or
                    request.content_type == 'application/json'
                )
                
                if is_api:
                    # Trả về JSON response cho API/AJAX
                    return JsonResponse({
                        'success': False,
                        'error': 'Rate limit exceeded',
                        'message': f'Bạn đã vượt quá giới hạn {max_requests} requests trong {period} giây.',
                        'retry_after': retry_after,
                        'rate_limit': {
                            'max_requests': max_requests,
                            'period': period,
                            'reset_at': int(request_data['reset_time'])
                        }
                    }, status=429)
                
                # Trả về HTML response từ template cho web
                html_content = render_rate_limit_template(
                    max_requests, 
                    period, 
                    retry_after
                )
                response = HttpResponse(html_content, status=429)
                response['Retry-After'] = str(retry_after)
                return response
            
            # Tiếp tục xử lý view bình thường
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def get_client_ip(request):
    """Lấy địa chỉ IP của client"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def render_rate_limit_template(rate_limit, rate_period, retry_after):
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
