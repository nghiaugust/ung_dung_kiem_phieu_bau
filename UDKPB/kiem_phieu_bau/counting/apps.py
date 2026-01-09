from django.apps import AppConfig


class CountingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'counting'
    
    def ready(self):
        import counting.signals  # Import signals để đăng ký
        # Scheduler sẽ được khởi động thủ công khi user bật toggle "Tự động kiểm phiếu"
