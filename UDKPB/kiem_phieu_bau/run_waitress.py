"""
Waitress WSGI Server Configuration for Windows
Thay thế Gunicorn trên Windows
"""
from waitress import serve
from kiem_phieu_bau.wsgi import application

if __name__ == '__main__':
    import socket
    
    # Lấy IP local để mobile app kết nối
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    print("=" * 60)
    print("🚀 Starting Waitress WSGI Server")
    print("=" * 60)
    print("📍 Host: 0.0.0.0 (Listening on all interfaces)")
    print("🔌 Port: 8000")
    print("🧵 Threads: 8 (Concurrent requests)")
    print("⏱️  Timeout: 120s (Upload timeout)")
    print()
    print("🌐 Access URLs:")
    print(f"   - Local:   http://127.0.0.1:8000")
    print(f"   - Network: http://{local_ip}:8000")
    print()
    print("📱 Mobile App Configuration:")
    print(f"   Base URL: http://{local_ip}:8000")
    print(f"   API Endpoint: http://{local_ip}:8000/api/")
    print("=" * 60)
    print("⚠️  Đảm bảo Firewall cho phép port 8000")
    print("⚠️  Mobile và PC phải cùng mạng WiFi")
    print("=" * 60)
    print("Press CTRL+C to quit")
    print()
    
    serve(
        application,
        host='0.0.0.0',  # Cho phép truy cập từ mọi IP (mobile app, máy khác)
        port=8000,
        threads=8,  # Tăng lên 8 threads cho 3-5 users đồng thời upload nhiều file
        channel_timeout=120,  # Tăng timeout lên 120s cho upload file lớn
        cleanup_interval=30,
        backlog=1024,  # Số connection chờ trong queue
        connection_limit=200,  # Giới hạn 200 connections đồng thời
        # Cho upload file lớn:
        recv_bytes=65536,  # Buffer size 64KB cho mỗi lần đọc
        send_bytes=65536,  # Buffer size 64KB cho mỗi lần ghi
    )
