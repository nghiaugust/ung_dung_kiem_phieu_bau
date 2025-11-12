"""
Authentication utilities cho API
"""
from functools import wraps
from django.http import JsonResponse
from django.utils import timezone
from .models import APIToken


def require_api_token(view_func):
    """
    Decorator đơn giản để check API token
    
    Usage:
        @require_api_token
        def my_api_view(request):
            user = request.api_user  # User đã authenticate
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Lấy token từ header
        auth_header = request.headers.get('Authorization', '')
        
        # Format: "Bearer <token>" hoặc "Token <token>"
        if not auth_header:
            return JsonResponse({
                'error': 'Missing authentication token',
                'message': 'Vui lòng cung cấp token xác thực'
            }, status=401)
        
        # Parse token
        try:
            scheme, token = auth_header.split(' ', 1)
            if scheme.lower() not in ['bearer', 'token']:
                raise ValueError()
        except ValueError:
            return JsonResponse({
                'error': 'Invalid authorization header',
                'message': 'Format header: Authorization: Bearer <token>'
            }, status=401)
        
        # Validate token
        try:
            api_token = APIToken.objects.select_related('user').get(
                token=token,
                is_active=True
            )
            
            # Check if user is active
            if not api_token.user.is_active:
                return JsonResponse({
                    'error': 'Account disabled',
                    'message': 'Tài khoản đã bị vô hiệu hóa'
                }, status=403)
            
            # Update last used timestamp
            api_token.last_used = timezone.now()
            api_token.save(update_fields=['last_used'])
            
            # Attach user to request
            request.api_user = api_token.user
            
        except APIToken.DoesNotExist:
            return JsonResponse({
                'error': 'Invalid token',
                'message': 'Token không hợp lệ hoặc đã hết hạn'
            }, status=401)
        
        # Call the view
        return view_func(request, *args, **kwargs)
    
    return wrapper


def optional_api_token(view_func):
    """
    Decorator cho phép token nhưng không bắt buộc
    Nếu có token hợp lệ thì attach user, không thì request.api_user = None
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        request.api_user = None
        
        if auth_header:
            try:
                scheme, token = auth_header.split(' ', 1)
                if scheme.lower() in ['bearer', 'token']:
                    api_token = APIToken.objects.select_related('user').get(
                        token=token,
                        is_active=True
                    )
                    if api_token.user.is_active:
                        request.api_user = api_token.user
                        api_token.last_used = timezone.now()
                        api_token.save(update_fields=['last_used'])
            except (ValueError, APIToken.DoesNotExist):
                pass
        
        return view_func(request, *args, **kwargs)
    
    return wrapper
