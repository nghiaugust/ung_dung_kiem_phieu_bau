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

WEB_PORT=8000
DB_PORT_HOST=3308
REDIS_PORT_HOST=6381
FLOWER_PORT=5555
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443

FLOWER_USER=admin
FLOWER_PASSWORD=admin
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

## 9. Loi thuong gap

Neu gap loi bind port (vi du 3306/6379 da bi app khac chiem), doi host port trong `docker/.env.docker`:

- `DB_PORT_HOST=3308` (hoac so khac)
- `REDIS_PORT_HOST=6381` (hoac so khac)

Sau do chay lai:

```bash
docker compose -f docker/docker-compose.yml down
docker compose -f docker/docker-compose.yml up -d --build
```

