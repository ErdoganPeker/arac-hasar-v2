# REPORT_TR — Addendum (2026-05-16 son güncellemeler)

Bu ek, `REPORT_TR.pdf` (v1, 2026-05-16 sabah) üretildikten sonra projeye uygulanan kalibrasyon ve altyapı değişikliklerini özetler. Bir sonraki PDF re-export sırasında bu içerik 7.4 ve 8.1 bölümlerine entegre edilmelidir.

## 1. Model Kalibrasyon (Model QA bulgularına yanıt)

| Parametre | Önceki | Yeni | Gerekçe |
|---|---|---|---|
| `damage_conf` | 0.25 | **0.28** | F1-curve peak (Model QA, n=281 val) |
| `parts_conf` | 0.30 | **0.25** | Parts recall bottleneck — unassigned %62 → %45-50 tahmini |
| `MIN_INTERSECTION_FOR_ASSIGNMENT` | 0.05 | **0.02** | Bbox-fallback ile birlikte %62 → ~0% (tek-foto test) |
| `crack` class | — | **`is_low_confidence_match=True` (zorunlu)** | mAP=0.14, recall=0.20 — müşteri-koruyucu uyarı |
| Severity model | aktif | **UI'da gizlenmesi tavsiye** | test_acc=0.57 (n=72), kullanılamaz seviyede |

`pipeline.py:347` ve `pipeline.py:487` dosyalarında uygulandı. Smoke testte `03_crack__000359.jpg` → conf=0.89 crack tespiti, **LOW_CONF flag ile dönüyor** (model emin olsa bile UI uyarı gösterir).

## 2. Pre-trained Model Ekosistemi

Custom modellerin yanına 6 entry / 4 composite kaynak eklendi:

- **`custom`** (CarDD üzerinde fine-tune edilmiş kendi pipeline'ımız) — varsayılan
- **`pretrained_ultralytics_yolo11m`** — Ultralytics COCO 80 sınıf, AGPL-3.0
- **`pretrained_roboflow_cardd`** — Roboflow Universe car-scratch-and-dent + car-parts-seg + severity ensemble, CC-BY-4.0
- **`pretrained_hybrid`** — Custom damage + Roboflow parts hibrit (eklenecek)

Frontend sağ üstte **"Model: ▼"** dropdown ile kullanıcı seçimi. `GET /api/v1/models` endpoint mevcut modellerin listesini döner; `POST /api/v1/inspect?model=<id>` query'si ile inference yönlendirilir. Response'a `model_source` ve `model_versions.pretrained_source` alanları eklendi.

**Disk:** ~458 MB pre-trained registry (Roboflow tam dahil), Ultralytics yalnız ~50 MB.

## 3. Deployment

Tam ücretsiz katmanla deploy planı `docs/DEPLOY_FREE.md`'de:
- **Vercel** (web, hobby plan) → hasari.vercel.app
- **Render Free** (backend) → hasari-api.onrender.com — *not: 512MB RAM ML için yetersiz; Render Starter $7/ay önerilir*
- **Supabase Free** (Postgres 500MB) + **Upstash Redis Free** + **Cloudflare R2** (10GB egress)
- **GitHub Actions** CI/CD: typecheck → deploy hook
- Tahmini ilk deploy süresi: ~60 dakika

## 4. Web Optimizasyon

| İyileştirme | Etki |
|---|---|
| `next/image` migration (3 lokasyon) | LCP ~3.8s → ~2.3s |
| ResultsTabs dynamic import | -40 KB first-load JS |
| `aspectRatio` containers | CLS 0.18-0.25 → <0.05 |
| Polling visibility-aware (30s hidden tab) | Battery -70% |
| Tahmini Lighthouse | Performance 86-92, SEO 95-100 |

## 5. SEO Hazırlık

- Bilingual metadata (TR ana, EN alt) hreflang
- JSON-LD Organization + WebApplication + WebSite
- Dynamic `sitemap.ts`, `robots.ts`
- OG image generator (1200x630, Next.js ImageResponse edge runtime)
- 10 hedef anahtar kelime (TR + EN)

## 6. Güvenlik (Production Launch Checklist'ten)

120 maddelik checklist `docs/PROD_LAUNCH_CHECKLIST.md`'de. Deploy öncesi TOP 10 P0:

1. `JWT_SECRET_KEY` 32+ char rastgele üret, Render env'e koy
2. `ROBOFLOW_API_KEY` revoke + yeniden üret (chat'te sızdı)
3. Next.js 15.1.3 → 15.5.16+ (CVE-2025-29927 middleware bypass)
4. WebSocket endpoint auth ekle (anonim erişim açık)
5. JWT `iss` + `aud` claim doğrulama
6. In-memory fallback prod'da hard-fail
7. Supabase pgBouncer pooler port (`:6543`) kullan
8. CORS regex `vercel.app` wildcard → spesifik origin
9. IDOR ownership check (her inspect endpoint'inde `user_id` filter)
10. KVKK uyumlu privacy policy + cookie consent

## 7. Bilinen Sınırlar (v0.1 → v0.2 köprüsü)

- **Crack class:** mAP=0.14 — retrain gerekiyor (cls_pw=4.0 + oversample, 18sa)
- **Severity model:** test_acc=0.57, gerçek labeled data ile yeniden eğitim şart (90 image kullanılamaz)
- **TR araç markası:** CarDD academic, Egea/Symbol/Clio underrepresented — TR pilot dataset gerekli (500 görsel etiketleme)
- **Gece/düşük ışık:** mAP ~0.25 — `hsv_v=0.7` augmentation ile retrain
- **Multi-foto async:** her görsel için ayrı sonuç değil, aggregate dönüyor — frontend per-image gösterimi v0.2

---

**Wave 6 + Wave 7 toplamı:** 11 ajan iş, 50+ dosya değişikliği, 12+ doküman, 1 teknik rapor PDF + bu addendum.

Tarih: 2026-05-16
Yazar: Erdoğan Yasin Peker
