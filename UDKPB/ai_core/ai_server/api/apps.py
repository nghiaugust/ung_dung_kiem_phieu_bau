from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    
    def ready(self):
        """
        Load models khi Django app khởi động
        Đảm bảo models được cache trong bộ nhớ ngay từ đầu
        """
        # Import ở đây để tránh lỗi AppRegistryNotReady
        from .model_services import TrOCRService, YOLOService
        
        print("\n" + "="*60)
        print("🚀 AI SERVER ĐANG KHỞI ĐỘNG...")
        print("="*60)
        
        try:
            # Khởi tạo TrOCR service (singleton)
            print("📦 Đang load TrOCR model...")
            trocr = TrOCRService()
            print("✅ TrOCR model đã sẵn sàng!")
            
            # Khởi tạo YOLO service (singleton)
            print("📦 Đang load YOLO model...")
            yolo = YOLOService()
            print("✅ YOLO model đã sẵn sàng!")
            
            print("="*60)
            print("✅ AI SERVER ĐÃ SẴN SÀNG XỬ LÝ REQUEST!")
            print("="*60 + "\n")
            
        except Exception as e:
            print(f"❌ LỖI LOAD MODELS: {e}")
            print("="*60 + "\n")
