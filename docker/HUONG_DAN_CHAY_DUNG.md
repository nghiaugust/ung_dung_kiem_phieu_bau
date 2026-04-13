# HUONG DAN NGAN: LENH CHAY VA DUNG

## DEV

Chay:
docker compose -f docker/docker-compose.dev.yml up -d --build

Dung:
docker compose -f docker/docker-compose.dev.yml down

## PROD

Chay:
docker compose -f docker/docker-compose.yml up -d --build

Dung:
docker compose -f docker/docker-compose.yml down
