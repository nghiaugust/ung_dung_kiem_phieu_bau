"""
Run Django Development Server on Local IP
Chạy Django development server với IP local để test qua network
"""
import socket
import os
import sys

def get_local_ip():
    """Lấy IP local của máy"""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        return local_ip
    except Exception as e:
        return None

if __name__ == '__main__':
    local_ip = get_local_ip()
    
    if not local_ip:
        print("❌ Không thể lấy IP local!")
        sys.exit(1)
    
    print("=" * 60)
    print("🚀 Starting Django Development Server")
    print("=" * 60)
    print(f"Hostname: {socket.gethostname()}")
    print(f"Local IP: {local_ip}")
    print(f"Port: 8000")
    print()
    print("🌐 Access URLs:")
    print(f"   - Local:   http://127.0.0.1:8000")
    print(f"   - Network: http://{local_ip}:8000")
    print()
    print("📱 Mobile App Configuration:")
    print(f"   Base URL: http://{local_ip}:8000")
    print(f"   API Endpoint: http://{local_ip}:8000/api/")
    print()
    print("💻 Benchmark Configuration:")
    print(f"   BASE_URL = \"http://{local_ip}:8000\"")
    print("=" * 60)
    print("⚠️  Đảm bảo Firewall cho phép port 8000")
    print("⚠️  Mobile và PC phải cùng mạng WiFi")
    print("=" * 60)
    print()
    
    # Chạy Django development server với IP local
    os.system(f"python manage.py runserver {local_ip}:8000")
