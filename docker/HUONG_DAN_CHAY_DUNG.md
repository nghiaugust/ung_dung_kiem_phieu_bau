# HUONG DAN NGAN: LENH CHAY VA DUNG

## DEV

Chay:
docker compose -f docker/docker-compose.dev.yml up -d --build

Dung:
docker compose -f docker/docker-compose.dev.yml down

## PROD

Chay:
docker compose -f docker/docker-compose.yml up -d --build

Tao tai khoản:
docker compose -f docker/docker-compose.yml exec web python manage.py shell -c "from account.models import Account; Account.objects.create_superuser('admin', email='admin@example.com', password='1')"

Dung:
docker compose -f docker/docker-compose.yml down

## Neu bi loi khi build pip install

Neu thay thong bao giong nhu:

- Temporary failure in name resolution
- Could not reach files.pythonhosted.org

thi do la loi DNS/mang tren may dang build Docker.

Cach xu ly nhanh:

1. Them bien sau vao `docker/.env.docker`:
PIP_INDEX_URL=https://pypi.org/simple

2. Neu van loi, cau hinh DNS trong Docker Desktop ve DNS on dinh (vi du 8.8.8.8, 1.1.1.1).

3. Build lai:
docker compose -f docker/docker-compose.yml build --no-cache celery-worker
