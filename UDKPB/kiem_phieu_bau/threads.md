# Chạy Gunicorn linux
gunicorn -c gunicorn_dev.py kiem_phieu_bau.wsgi:application

# Chạy waitress 
cd kiem_phieu_bau
python run_waitress.py