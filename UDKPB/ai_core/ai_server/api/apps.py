from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        """
        Load the enabled AI services once when the Django app starts.
        """
        from .model_services import MODEL_SERVICE_CLASSES, get_enabled_model_keys

        print("\n" + "=" * 60)
        print("AI SERVER STARTING")
        print("=" * 60)

        try:
            enabled_model_keys = get_enabled_model_keys()
            print(f"Enabled models: {', '.join(enabled_model_keys) or 'none'}")

            for model_key in enabled_model_keys:
                print(f"Loading {model_key}...")
                MODEL_SERVICE_CLASSES[model_key]()
                print(f"{model_key} ready")

            print("=" * 60)
            print("AI SERVER READY")
            print("=" * 60 + "\n")
        except Exception as exc:
            print(f"MODEL LOAD ERROR: {exc}")
            print("=" * 60 + "\n")
