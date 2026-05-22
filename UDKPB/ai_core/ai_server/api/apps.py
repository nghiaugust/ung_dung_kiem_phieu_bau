from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        """
        Load models when the Django app starts so they are cached in memory.
        """
        from .model_services import VietNameOCRService, YOLOService

        print("\n" + "=" * 60)
        print("AI SERVER DANG KHOI DONG...")
        print("=" * 60)

        try:
            print("Dang load VietNameOCR model...")
            VietNameOCRService()
            print("VietNameOCR model da san sang!")
        except Exception as exc:
            print(f"VietNameOCR model khong nap duoc (optional): {exc}")

        try:
            print("Dang load YOLO model...")
            YOLOService()
            print("YOLO model da san sang!")
        except Exception as exc:
            print(f"LOI LOAD YOLO MODEL: {exc}")

        print("=" * 60)
        print("AI SERVER DA SAN SANG XU LY REQUEST!")
        print("=" * 60 + "\n")
