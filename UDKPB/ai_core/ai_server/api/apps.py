from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        """
        Load the three AI services once when the Django app starts.
        """
        from .model_services import ResNet18CrossedService, VietNameOCRService, YOLOXService

        print("\n" + "=" * 60)
        print("AI SERVER STARTING")
        print("=" * 60)

        try:
            print("Loading model_vietnameocr...")
            VietNameOCRService()
            print("model_vietnameocr ready")

            print("Loading model_yolo_x...")
            YOLOXService()
            print("model_yolo_x ready")

            print("Loading model_resnet18_crossed...")
            ResNet18CrossedService()
            print("model_resnet18_crossed ready")

            print("=" * 60)
            print("AI SERVER READY")
            print("=" * 60 + "\n")
        except Exception as exc:
            print(f"MODEL LOAD ERROR: {exc}")
            print("=" * 60 + "\n")
