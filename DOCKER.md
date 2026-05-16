# Docker — Full Stack (web + api + worker + db + redis + minio)

Tüm stack tek komutla ayağa kalkar. Compose dosyası `services/backend/docker-compose.yml`
içinde toplanmıştır; web servisi monorepo kökünden build edilir (`apps/web/Dockerfile`).

## Tek komutluk başlatma

```bash
cd services/backend
docker compose up --build
```

İlk çalıştırmada Next.js standalone build + Python image build birkaç dakika sürer.
Sonraki çalıştırmalar layer cache sayesinde çok daha hızlıdır.

## Servis URL'leri (host'tan erişim)

| Servis              | URL                                  | Açıklama                                  |
|---------------------|--------------------------------------|-------------------------------------------|
| Web (Next.js 15)    | http://localhost:3000                | App Router, standalone output             |
| API (FastAPI)       | http://localhost:8000                | REST + WebSocket                          |
| API docs (Swagger)  | http://localhost:8000/docs           | OpenAPI UI                                |
| MinIO Console       | http://localhost:9001                | minioadmin / minioadmin                   |
| MinIO S3 endpoint   | http://localhost:9000                | S3 protokol                               |
| Postgres            | localhost:5432                       | postgres / postgres / arac_hasar          |
| Redis               | localhost:6379                       | Celery broker + cache                     |

## Yararlı komutlar

```bash
# Arka planda
docker compose up -d --build

# Sadece web'i yeniden build
docker compose build web && docker compose up -d web

# Logları izle
docker compose logs -f web api worker

# Hepsini durdur (volume'ları korur)
docker compose down

# Volume'larla beraber sil (DB sıfırlanır)
docker compose down -v
```

## NEXT_PUBLIC_API_URL hakkında

`NEXT_PUBLIC_*` env'leri Next.js'te **build-time'da bundle'a gömülür**, runtime'da
değiştirilemez. Browser, `web` container'ından değil kullanıcının makinesinden istek
yaptığı için varsayılan `http://localhost:8000` doğrudur (host port mapping ile API'ye
ulaşır). Production'da farklı bir host kullanılacaksa:

```bash
NEXT_PUBLIC_API_URL=https://api.example.com docker compose build web
```

Container-içi server-side fetch (RSC, route handlers) için `INTERNAL_API_URL=http://api:8000`
runtime env'i mevcuttur — Docker network üzerinden DNS ile API'ye erişir.

## GPU notu

`api` ve `worker` servisleri NVIDIA GPU bekler (`deploy.resources.reservations.devices`).
GPU yoksa bu blokları yorum satırına alın veya `docker compose up db redis minio web api`
şeklinde seçici başlatın.
