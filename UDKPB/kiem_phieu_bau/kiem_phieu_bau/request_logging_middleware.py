"""
Request Logging Middleware
Hiển thị log requests giống như runserver khi dùng Waitress
"""
import logging
import time

logger = logging.getLogger('django.server')


class RequestLoggingMiddleware:
    """
    Middleware để log tất cả HTTP requests
    Hiển thị method, path, status code, và response time
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Lưu thời gian bắt đầu request
        start_time = time.time()
        
        # Xử lý request
        response = self.get_response(request)
        
        # Tính response time
        duration = time.time() - start_time
        duration_ms = duration * 1000
        
        # Lấy thông tin request
        method = request.method
        path = request.get_full_path()
        status_code = response.status_code
        
        # Màu cho status code (nếu terminal hỗ trợ)
        if 200 <= status_code < 300:
            status_display = f"\033[92m{status_code}\033[0m"  # Green
        elif 300 <= status_code < 400:
            status_display = f"\033[94m{status_code}\033[0m"  # Blue
        elif 400 <= status_code < 500:
            status_display = f"\033[93m{status_code}\033[0m"  # Yellow
        else:
            status_display = f"\033[91m{status_code}\033[0m"  # Red
        
        # Log request (giống runserver format)
        log_message = f'"{method} {path}" {status_display} [{duration_ms:.2f}ms]'
        
        # Sử dụng level phù hợp
        if status_code >= 500:
            logger.error(log_message)
        elif status_code >= 400:
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        return response
