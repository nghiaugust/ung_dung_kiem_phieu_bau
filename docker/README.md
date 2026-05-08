# UDKPB Docker Quick Start (sau khi git clone)

Tai lieu nay chi tap trung vao tung buoc de chay duoc Docker nhanh nhat.

## 1. Dieu kien can

- Da cai Docker Desktop
- Docker Compose da san sang (`docker compose version` chay duoc)

## 2. Clone code va vao thu muc du an

```bash
git clone <repo-url>
cd ung_dung_kiem_phieu_bau
```

## 3. Tao file moi truong Docker (neu chua co)

Neu trong repo chua co file `docker/.env.docker`, tao file nay voi noi dung toi thieu:

```env
DEBUG=False
SECRET_KEY=replace-this-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost,http://127.0.0.1

DB_ENGINE=django.db.backends.mysql
DB_NAME=udkpb
DB_USER=udkpb_user
DB_PASSWORD=udkpb_password
DB_HOST=mysql
DB_PORT=3306
DB_ROOT_PASSWORD=rootpassword

REDIS_HOST=redis
REDIS_PORT=6379
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
AI_SERVER_BASE_URL=http://ai-server:8082

WEB_PORT=8000
AI_PORT_HOST=8082
DB_PORT_HOST=3308
REDIS_PORT_HOST=6381
FLOWER_PORT=5555
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443

FLOWER_USER=admin
FLOWER_PASSWORD=admin

# Tuy chon: mirror PyPI neu mang bi chan/chap chon
PIP_INDEX_URL=https://pypi.org/simple
```

## 4. Chay Docker (PROD compose)

Chay tu thu muc goc du an (`ung_dung_kiem_phieu_bau`):

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

## 5. Kiem tra container

```bash
docker compose -f docker/docker-compose.yml ps
```

Neu can xem log:

```bash
docker compose -f docker/docker-compose.yml logs -f web
docker compose -f docker/docker-compose.yml logs -f celery-worker
docker compose -f docker/docker-compose.yml logs -f ai-server
```

Neu chi muon khoi dong rieng AI server:

```bash
docker compose -f docker/docker-compose.yml up -d --build ai-server
```

## 6. Truy cap web

- Trang web: `http://localhost`
- Admin: `http://localhost/admin/login/`
- Truy cap truc tiep Django: `http://localhost:8000`

## 7. Dung he thong

```bash
docker compose -f docker/docker-compose.yml down
```

## 8. Tuy chon: Chay DEV compose

```bash
docker compose -f docker/docker-compose.dev.yml up -d --build
docker compose -f docker/docker-compose.dev.yml ps
docker compose -f docker/docker-compose.dev.yml down
```

Mac dinh DEV map port:

- MySQL: `3307`
- Redis: `6380`
- Web: `8001`
- AI Server: `8080`

## 9. Loi thuong gap

Neu gap loi bind port (vi du 3306/6379 da bi app khac chiem), doi host port trong `docker/.env.docker`:

- `DB_PORT_HOST=3308` (hoac so khac)
- `REDIS_PORT_HOST=6381` (hoac so khac)

Sau do chay lai:

```bash
docker compose -f docker/docker-compose.yml down
docker compose -f docker/docker-compose.yml up -d --build
```

## 10. Neu bi loi DNS khi pip install trong Docker build

Neu log co dang:

- Temporary failure in name resolution
- Could not reach files.pythonhosted.org / pypi.org

Thi day la loi mang/DNS cua moi truong Docker tren may do, khong phai loi code app.

Cach xu ly uu tien:

1. Dat mirror pip trong `docker/.env.docker` (hoac file `.env` ma ban dung voi compose):

```env
PIP_INDEX_URL=https://pypi.org/simple
```

Neu don vi co mirror noi bo, thay bang URL mirror noi bo.

2. Neu van loi, cau hinh DNS trong Docker Desktop (Settings -> Docker Engine), them DNS on dinh vi du:

```json
{
	"dns": ["8.8.8.8", "1.1.1.1"]
}
```

3. Build lai:

```bash
docker compose -f docker/docker-compose.yml build --no-cache celery-worker
docker compose -f docker/docker-compose.yml up -d
```

## 11. Neu bi loi trung port 8080 khi chay ai-server

Neu gap loi dang:

- ports are not available ... bind ... 0.0.0.0:8080

Thi doi host port cho AI server:

```powershell
$env:AI_PORT_HOST='8082'
docker compose -f docker/docker-compose.yml up -d --build ai-server
```

Hoac dat co dinh trong `docker/.env.docker`:

```env
AI_PORT_HOST=8082
```

Khi do mobile app goi AI qua `http://<LAN_IP>:8082`.

