# HUONG DAN NGAN: LENH CHAY VA DUNG

## DEV

Chay:
docker compose -f docker/docker-compose.dev.yml up -d --build

Chi chay AI server (DEV):
docker compose -f docker/docker-compose.dev.yml up -d --build ai-server

Dung:
docker compose -f docker/docker-compose.dev.yml down

## PROD

Chay:
docker compose -f docker/docker-compose.yml up -d --build

Chi chay AI server (PROD):
docker compose -f docker/docker-compose.yml up -d --build ai-server

Tao tai khoản:
docker compose -f docker/docker-compose.yml exec web python manage.py shell -c "from account.models import Account; Account.objects.create_superuser('admin1', email='admin1@example.com', password='1')"

hoặc reset admin:
docker compose -f docker-compose.yml exec web python manage.py shell -c "from account.models import Account; u=Account.objects.get(username='admin'); u.set_password('1'); u.email='admin@example.com'; u.save(); print('updated admin')"

Dung:
docker compose -f docker/docker-compose.yml down

Xem log AI server:
docker compose -f docker/docker-compose.yml logs -f ai-server

## Neu loi trung port 8080 (Windows)

Loi thuong gap:
ports are not available ... bind ... 0.0.0.0:8080

Nguyen nhan: may ban da co process khac dang dung port 8080.

Cach nhanh nhat (doi port host cho AI server):

PowerShell tam thoi cho phien hien tai:
$env:AI_PORT_HOST='8082'
docker compose -f docker/docker-compose.yml up -d --build ai-server

Hoac set co dinh trong docker/.env.docker:
AI_PORT_HOST=8082

Sau do app/mobile goi AI theo port moi:
http://<LAN_IP_MAY_TINH>:8082/api/health/

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
