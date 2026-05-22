"""
Waitress WSGI Server Configuration for AI Server
Chạy 1 process để model AI chỉ load 1 lần (tiết kiệm RAM)
Chạy 4 threads để server vẫn xử lý nhiều requests đồng thời
"""
import os
import sys
import logging
from waitress import serve

# Setup Django before importing application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_server.settings')
import django
django.setup()

from ai_server.wsgi import application

# Import model services để load model trước khi server chạy
from api.model_services import TrOCRService, YOLOService

# Configure logging to show requests
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%d/%b/%Y %H:%M:%S',
    stream=sys.stdout
)

if __name__ == '__main__':
    import socket
    
    # Lấy IP local để các service khác kết nối
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    # Initialize YOLO (required)
    try:
        yolo_service = YOLOService()
        print("✅ YOLO Model loaded successfully")
    except Exception as e:
        print(f"❌ Error loading YOLO (required): {e}")
        sys.exit(1)
    
    # Initialize TrOCR (optional - skip if error)
    try:
        trocr_service = TrOCRService()
        print("✅ TrOCR Model loaded successfully")
    except Exception as e:
        print(f"⚠️ TrOCR Model failed (optional): {e}")
        print("   Continuing with YOLO only...")
    
    print("-" * 70)
    print("Process: 1 Threads: 4 ")
    print("Timeout: 300s (AI processing timeout)")
    print()
    print("Access URLs:")
    print(f"   - Local:   http://127.0.0.1:8081")
    print(f"   - Network: http://{local_ip}:8081")
    print()
    
    serve(
        application,
        host='0.0.0.0',  # Cho phép truy cập từ mọi IP
        port=8081,
        
        # QUAN TRỌNG: Cấu hình cho single process + multi-thread
        threads=4,  # 4 threads để xử lý đồng thời 4 requests
        # NOTE: Không set workers parameter vì waitress không hỗ trợ multi-process
        # Waitress chỉ chạy single process, nhưng có thể multi-thread
        
        # Timeout cao cho AI processing (TrOCR + YOLO)
        channel_timeout=300,  # 5 phút cho mỗi request
        
        # Connection settings
        backlog=256,  # Queue size cho connections đang chờ
        connection_limit=100,  # Tối đa 100 connections đồng thời
        
        # Buffer settings cho image upload
        recv_bytes=65536,  # 64KB buffer cho upload
        send_bytes=65536,  # 64KB buffer cho response
        
        # Cleanup
        cleanup_interval=30,  # Cleanup mỗi 30s
        
        # Error handling
        asyncore_use_poll=True,  # Better performance trên Windows
        
        # Expose server
        expose_tracebacks=True,  # Debug mode
        clear_untrusted_proxy_headers=False,
    )
