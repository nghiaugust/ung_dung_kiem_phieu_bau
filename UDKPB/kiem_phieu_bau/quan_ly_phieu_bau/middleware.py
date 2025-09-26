from django.shortcuts import redirect
from django.conf import settings
from django.contrib import messages
from django.urls import resolve

from django.urls import resolve
from django.utils.deprecation import MiddlewareMixin

class LoginRequiredMessageMiddleware(MiddlewareMixin):
    """
    Middleware: Nếu chưa đăng nhập và truy cập view cần đăng nhập, sẽ redirect về login kèm message.
    """
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Không áp dụng cho các view login, static, media
        login_url = settings.LOGIN_URL if hasattr(settings, 'LOGIN_URL') else '/login/'
        allowed_names = ['login_view', 'login', 'logout_view', 'logout']
        # Lấy tên view hiện tại
        try:
            match = resolve(request.path)
            if match.url_name in allowed_names:
                return None
        except:
            return None
        # Nếu chưa đăng nhập
        if not request.user.is_authenticated:
            messages.warning(request, 'Bạn cần đăng nhập để truy cập chức năng này!')
            from django.shortcuts import redirect
            return redirect(f"{login_url}?next={request.path}")
        return None
