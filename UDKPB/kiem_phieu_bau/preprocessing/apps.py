from django.apps import AppConfig


class PreprocessingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'preprocessing'
    
    def ready(self):
        import preprocessing.signals  # Import signals để đăng ký
