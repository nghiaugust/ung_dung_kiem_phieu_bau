# Gunicorn Configuration - Development Testing
# File này để test multi-workers trên Windows

# Workers
workers = 3  # 3 workers = xử lý 3 requests đồng thời

# Bind
bind = "127.0.0.1:8000"

# Timeouts
timeout = 120  # 2 phút cho upload file lớn

# Logging
accesslog = "-"  # Log to console
errorlog = "-"
loglevel = "info"

# Development
reload = True  # Auto-reload khi code thay đổi (như runserver)

print("=" * 60)
print("🚀 GUNICORN DEVELOPMENT MODE")
print("=" * 60)
print(f"Workers: {workers}")
print(f"URL: http://127.0.0.1:8000")
print(f"Auto-reload: {reload}")
print("=" * 60)
