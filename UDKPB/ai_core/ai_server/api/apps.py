from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        """
        Load enabled models when the Django app starts so they are cached in memory.
        """
        from .model_services import MODEL_SERVICE_CLASSES, get_enabled_model_keys

        print("\n" + "=" * 60)
        print("AI SERVER DANG KHOI DONG...")
        print("=" * 60)

        try:
            enabled_model_keys = get_enabled_model_keys()
            print(f"Enabled models: {', '.join(enabled_model_keys) or 'none'}")
            for model_key in enabled_model_keys:
                print(f"Dang load {model_key}...")
                MODEL_SERVICE_CLASSES[model_key]()
                print(f"{model_key} da san sang!")
        except Exception as exc:
            print(f"LOI LOAD MODEL: {exc}")

        print("=" * 60)
        print("AI SERVER DA SAN SANG XU LY REQUEST!")
        print("=" * 60 + "\n")
