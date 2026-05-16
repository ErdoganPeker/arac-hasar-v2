# Gözlemlenebilirlik Kurulum Rehberi

Üç katmanlı bir izleme sistemi: hata takibi (Sentry), metrikler (Prometheus + Grafana), yapısal log (loglar zaten stdout'a + Sentry'ye gidiyor).

## 1. Sentry — Hata Takibi

### Kurulum

1. sentry.io'ya kayıt ol (free tier 5000 event/ay yeter)
2. İki proje oluştur: `backend-python` ve `mobile-react-native`
3. DSN'leri kopyala

### Backend entegrasyonu

`backend_main.py`'nin başına ekle:

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        integrations=[
            FastApiIntegration(),
            CeleryIntegration(),
        ],
        environment=settings.environment,
        release=settings.release_version,
    )
```

### Mobil entegrasyonu

```bash
npx @sentry/wizard@latest -i reactNative
```

Wizard otomatik konfigüre eder. `App.tsx` başında:

```typescript
import * as Sentry from '@sentry/react-native';

Sentry.init({
  dsn: process.env.EXPO_PUBLIC_SENTRY_DSN,
  tracesSampleRate: 0.2,
});

export default Sentry.wrap(App);
```

### Faydalı alertler

- Yeni error type ilk 1 saatte 5'ten fazla → Slack
- Crash-free user rate 24h içinde %98'in altına düşerse → Slack
- p95 transaction duration 3s'yi aşarsa → Slack

---

## 2. Prometheus — Metrikler

### Backend tarafı

`backend_main.py`'a ekle:

```python
from prometheus_fastapi_instrumentator import Instrumentator

instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    excluded_handlers=["/healthz", "/metrics"],
)
instrumentator.instrument(app).expose(app, endpoint="/metrics")
```

Bu otomatik olarak şunları ekler:
- `http_requests_total{method, status, handler}`
- `http_request_duration_seconds{handler}` (histogram)
- `http_requests_in_progress`

### Custom ML metrikleri

`backend_ml_service.py` içine ekle:

```python
from prometheus_client import Counter, Histogram

ml_inferences = Counter(
    'ml_inferences_total',
    'Toplam ML inference sayisi',
    ['status']
)
ml_inference_duration = Histogram(
    'ml_inference_duration_seconds',
    'ML inference suresi',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
)
ml_damage_count = Histogram(
    'ml_damage_count_per_image',
    'Goruntude bulunan hasar sayisi',
    buckets=[0, 1, 2, 3, 5, 10, 20]
)

# analyze() icinde:
with ml_inference_duration.time():
    try:
        result = self._pipeline.analyze(image)
        ml_inferences.labels(status='success').inc()
        ml_damage_count.observe(result.get('damage_count', 0))
        return result
    except Exception:
        ml_inferences.labels(status='error').inc()
        raise
```

### Prometheus config

`observability/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'api'
    static_configs:
      - targets: ['api:8000']
    metrics_path: /metrics

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'nvidia-gpu'
    static_configs:
      - targets: ['dcgm-exporter:9400']

rule_files:
  - alerts.yml
```

### docker-compose'a ekle

```yaml
prometheus:
  image: prom/prometheus:latest
  volumes:
    - ./observability/prometheus.yml:/etc/prometheus/prometheus.yml
    - ./observability/alerts.yml:/etc/prometheus/alerts.yml
    - prom_data:/prometheus
  ports:
    - "9090:9090"

node-exporter:
  image: prom/node-exporter:latest
  ports:
    - "9100:9100"

dcgm-exporter:
  image: nvcr.io/nvidia/k8s/dcgm-exporter:latest
  ports:
    - "9400:9400"
  runtime: nvidia
```

---

## 3. Grafana — Görselleştirme

### Kurulum

```yaml
# docker-compose.yml
grafana:
  image: grafana/grafana:latest
  ports:
    # Host 3001 -> container 3000 to avoid clashing with Next.js web dev server on 3000.
    - "3001:3000"
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=admin
  volumes:
    - grafana_data:/var/lib/grafana
    - ./observability/grafana_dashboard.json:/var/lib/grafana/dashboards/main.json
```

http://localhost:3001 - admin/admin. (Note: port 3000 is reserved for the Next.js web app — see [QUICKSTART_DEMO.md](QUICKSTART_DEMO.md).)

İlk girişte:
1. Data source ekle: Prometheus → http://prometheus:9090
2. Dashboard import et: observability/grafana_dashboard.json

### İzlenecek 6 Ana Metrik

1. **API throughput:** requests/sec, status code breakdown
2. **API latency:** p50, p95, p99 per endpoint
3. **ML inference time:** distribution histogram
4. **ML success rate:** success vs error oranı
5. **GPU utilization:** % kullanım, VRAM
6. **Damages found per inspection:** histogram - kullanıcı kalıp dağılımı

---

## 4. Yapısal Log

Loglar zaten stdout'a gidiyor — Docker JSON driver veya bir log aggregator (Loki, ELK, Datadog) ile topla.

Önerilen format:

```python
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'trace_id': getattr(record, 'trace_id', None),
        }
        if record.exc_info:
            log['exception'] = self.formatException(record.exc_info)
        return json.dumps(log)
```

Her log satırı JSON → Loki/ELK'da regex değil field bazlı arama.

---

## 5. Uyarılar (Alerting)

`observability/alerts.yml`:

```yaml
groups:
  - name: api_alerts
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "5xx error rate > 5%"

      - alert: HighLatency
        expr: histogram_quantile(0.95, http_request_duration_seconds_bucket) > 5
        for: 10m
        labels:
          severity: warning

      - alert: GPUOOM
        expr: nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes > 0.95
        for: 5m
        labels:
          severity: critical

      - alert: MLInferenceFailureRate
        expr: rate(ml_inferences_total{status="error"}[10m]) > 0.10
        for: 5m
        labels:
          severity: critical
```

Alertmanager → Slack webhook entegrasyonu için Slack'te bir incoming webhook oluştur ve alertmanager config'ine ekle.

---

## Maliyet

Bu stack'in tamamı self-hosted olarak küçük bir VPS'te (4GB RAM) ~$20/ay'a çalışabilir. Yönetim istemiyorsan:

- **Sentry SaaS:** Free 5K event/ay → Team $26/ay (50K event)
- **Grafana Cloud Free:** 10K series, 50GB log → Pro $49+/ay
- **Datadog:** Hepsi tek elden ama pahalı, $15+ per host/ay

MVP için self-hosted yeter, ölçek artınca SaaS'a geç.
