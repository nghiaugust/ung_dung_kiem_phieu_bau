"""
Custom middleware để tối ưu performance và logging
"""
import time
import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class PerformanceLoggingMiddleware(MiddlewareMixin):
    """
    Middleware để log thời gian xử lý request
    """
    
    def process_request(self, request):
        """Bắt đầu timing"""
        request._start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """Log thời gian xử lý"""
        if hasattr(request, '_start_time'):
            duration = time.time() - request._start_time
            
            # Log cho API requests
            if request.path.startswith('/api/'):
                # Lấy info
                method = request.method
                path = request.path
                status = response.status_code
                
                # Log với color
                if status < 400:
                    log_func = logger.info
                    status_label = "[OK]"
                elif status < 500:
                    log_func = logger.warning
                    status_label = "[WARN]"
                else:
                    log_func = logger.error
                    status_label = "[ERROR]"
                
                log_func(
                    f"{status_label} {method} {path} - {status} - {duration:.3f}s"
                )
        
        return response


class RequestSizeLimitMiddleware(MiddlewareMixin):
    """
    Middleware để giới hạn kích thước request (tránh upload file quá lớn)
    """
    
    # Giới hạn: 100MB
    MAX_UPLOAD_SIZE = 100 * 1024 * 1024
    
    def process_request(self, request):
        """Kiểm tra kích thước request"""
        if request.method == 'POST':
            content_length = request.META.get('CONTENT_LENGTH')
            if content_length:
                content_length = int(content_length)
                if content_length > self.MAX_UPLOAD_SIZE:
                    from django.http import JsonResponse
                    return JsonResponse({
                        'success': False,
                        'error': f'Request quá lớn. Giới hạn: {self.MAX_UPLOAD_SIZE / 1024 / 1024}MB'
                    }, status=413)
        
        return None
