# Tải redis
https://github.com/tporadowski/redis/releases

# Terminal celery
cd UDKPB/kiem_phieu_bau

# Terminal 1: worker cho upload
celery -A kiem_phieu_bau worker -Q upload_queue --pool=gevent --concurrency=1 --hostname=upload_worker@%h -l info

# Terminal 2: worker cho count
celery -A kiem_phieu_bau worker -Q counting_queue --pool=gevent --concurrency=1 --hostname=counting_worker1@%h -l info

# Terminal 3: worker cho count
celery -A kiem_phieu_bau worker -Q counting_queue --pool=gevent --concurrency=1 --hostname=counting_worker2@%h -l info


# ====================================
# MONITORING & DEBUGGING
# ====================================

# Xem danh sách tasks đang được xử lý (active)
celery -A kiem_phieu_bau inspect active

# Xem tasks đã lấy từ queue nhưng chưa xử lý (reserved/prefetched)
celery -A kiem_phieu_bau inspect reserved

# Xem tasks đã được schedule (chờ thời gian thực thi)
celery -A kiem_phieu_bau inspect scheduled

# Xem stats chi tiết của từng worker
celery -A kiem_phieu_bau inspect stats

# Ping workers (kiểm tra còn sống không)
celery -A kiem_phieu_bau inspect ping

# ====================================
# XEM SỐ TASKS ĐANG CHỜ TRONG QUEUE
# ====================================

# Cách 1: Dùng redis-cli (CHÍNH XÁC NHẤT)
redis-cli

# Trong redis-cli, chạy:
LLEN upload_queue
LLEN counting_queue
LLEN default

# Hoặc xem tất cả keys:
KEYS *queue*

# Thoát redis-cli:
exit

# Cách 2: Một dòng lệnh (PowerShell)
redis-cli LLEN upload_queue
redis-cli LLEN counting_queue
redis-cli LLEN default

# Cách 3: Xem tất cả info về queues
redis-cli INFO keyspace