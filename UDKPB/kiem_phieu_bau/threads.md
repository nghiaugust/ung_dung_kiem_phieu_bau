# Chạy Gunicorn linux
gunicorn -c gunicorn_dev.py kiem_phieu_bau.wsgi:application

# Chạy waitress 
cd kiem_phieu_bau
python run_waitress.py


# Terminal 1: HTTP API (port 8000)
python run_waitress.py

# Terminal 2: WebSocket (port 8001)
daphne -b 0.0.0.0 -p 8001 kiem_phieu_bau.asgi:application