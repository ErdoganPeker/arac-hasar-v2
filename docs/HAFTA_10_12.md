# Hafta 10–12 Detaylı Rehber: Gözlemlenebilirlik, Pilot, Lansman

Bu son faz, çalışan sistemini **gerçek kullanıcılara ulaştırır**. Hedef MVP lansman: 20-50 pilot kullanıcı, ölçülen metrik, ilk geri bildirim döngüsü.

## Faz 4 Sonu Hedefler

- Üretimde Sentry + Prometheus + Grafana aktif
- 50+ test case'lik regression suite, CI'da koşuyor
- 1-2 sigorta acentesi pilot programında veya 20-30 B2C beta kullanıcısı
- Public landing page + APK + TestFlight
- v2 backlog dokümante

## Dosya Haritası (Yeni Eklenenler)

```
mvp-arac-hasar/
├── (Faz 1-3 dosyaları)
├── HAFTA_10_12_REHBER.md
├── tests/
│   ├── regression_test.py        # 50 test case ile regression
│   └── test_cases.yaml           # Test case tanimlari
├── observability/
│   ├── README.md                  # Sentry + Prometheus + Grafana kurulum
│   ├── grafana_dashboard.json     # Hazir dashboard
│   ├── prometheus.yml             # Prometheus config
│   └── alerts.yml                 # Uyari kurallari
├── pilot/
│   ├── ONBOARDING.md              # Pilot kullanici karşilama
│   ├── FEEDBACK_FORM.md           # Geri bildirim sablonu
│   └── PILOT_AGREEMENT.md         # B2B pilot anlasma sablonu
└── LAUNCH_CHECKLIST.md            # Lansman oncesi tum kontroller
```

---

## Hafta 10: Gözlemlenebilirlik

### Neden bu hafta önemli?

Üretime çıkıp 1 hafta sonra "bir şeyler yavaşladı" diyemezsin. Önceden ölçmen lazım: hangi endpoint kaç ms, hangi model kaç hata veriyor, kullanıcı nerede vazgeçiyor.

### Gün 1: Sentry (hata takibi)

Backend'e ve mobil app'e Sentry SDK ekle. Free tier ay başına 5000 event yeter, MVP için bol.

Backend için `main.py`'nin başına:
```python
import sentry_sdk
sentry_sdk.init(
    dsn=settings.sentry_dsn,
    traces_sample_rate=0.1,  # %10 trace
    profiles_sample_rate=0.1,
)
```

Mobil için:
```bash
npx expo install @sentry/react-native
```

### Gün 2: Prometheus + Grafana (metrikler)

3 katman metrik:
1. **Sistem:** CPU, RAM, GPU utilization (nvidia-exporter)
2. **API:** Request rate, latency p50/p95/p99, error rate per endpoint
3. **ML:** Inference latency, model confidence dağılımı, "hasar bulundu" oranı

`observability/prometheus.yml` ve hazır `grafana_dashboard.json` import et.

### Gün 3: Yapısal log + trace

Backend her request'e trace ID ekler:
```python
import uuid
@app.middleware("http")
async def trace_middleware(request, call_next):
    trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response
```

Mobil de her API call'a kendi trace ID'sini gönderir. Sentry, Grafana, log dosyaları hepsi aynı ID ile birbirine bağlanır.

### Gün 4: Regression test suite

`tests/test_cases.yaml` içinde 50 case tanımla. Her case:
- Bir input görüntü (sabit URL)
- Beklenen sonuçlar (en azından: hasar var/yok, ±%20 maliyet aralığı)

`regression_test.py` her PR'da koşar. Yeni model versiyonu çıkarınca:
```bash
python tests/regression_test.py --weights new_model.pt
# Eski model'e göre kayıp var mı kontrol et
```

### Gün 5: Uyarı kuralları

Sentry'de:
- Error rate %5'i aştığında Slack'e bildirim
- p95 latency 5 saniyeyi aştığında

Prometheus alertmanager:
- GPU kullanımı %95+ → ölçeklendir
- Disk %85+ → eski görüntüleri temizle
- DB connection pool tükendi

---

## Hafta 11: Pilot Çalışması

### İki paralel kanal

**B2B yolu — sigorta acentesi/eksper pilotu:**

Hedef: 1-2 küçük sigorta acentesi veya bağımsız ekspertiz firması. İdeal profil: dijital benimseme arzulu, küçük ölçekli (ayda 50-200 hasar dosyası).

İletişim stratejisi:
- LinkedIn ile sektörü tara (insurance, claims adjuster, hasar uzmanı)
- TSB üye listesini incele, küçük olanlara odaklan
- İlk e-posta: 30 saniyede özet + 5 örnek görüntü sonucu + "1 hafta ücretsiz deneme"
- Demo: 30 dk Zoom — canlı görüntü ile sistemi göster

İlk pilotun değer önerisi:
- Eksper başına günlük 2-3 saat tasarruf
- Tutarsızlık azalması (aynı hasar farklı eksper farklı fiyat sorunu)
- Mobil dosya hızlandırma

**B2C yolu — son kullanıcı beta:**

Hedef: 20-30 erken benimseyen. İdeal:
- Sahibinden.com araç satıcıları (alıcıya hasar raporu)
- Oto-pazar dükkanları (envanter değerlendirme)
- Kasko sahibi sürücüler (hasar öncesi/sonrası dokümantasyon)

Kanal: Reddit r/TurkeyJobs, Instagram oto-paylaşım sayfaları, ücretsiz Google Ads (200-500 TL/ay).

### Gün 1–2: Pilot onboarding

`pilot/ONBOARDING.md`'yi her yeni kullanıcıya yolla:
- 5 dakikalık video tutorial (kendi çekersin, kaba olabilir)
- WhatsApp grubu — geri bildirim için
- Hafta sonu "office hours" — sorulara cevap

### Gün 3–5: Veri toplama + iterasyon

Her gün sabah 10 dakika:
- Sentry'de yeni hatalar var mı
- Grafana'da anormal pattern
- WhatsApp grubunda yeni geri bildirim
- DB'de "hasar bulundu" oranı stabil mi

Haftalık sprint: en kritik 3 bug + en şikayet edilen 1 UX değişikliği.

---

## Hafta 12: Lansman ve Devam Planı

### Gün 1–2: Lansman önü check

`LAUNCH_CHECKLIST.md` ile bir bir kontrol:
- API endpoint'leri çalışıyor mu (canary test)
- Mobil app TestFlight + Google Play Internal'da hatasız
- Landing page yayında
- KVKK aydınlatma metni var mı
- Müşteri destek e-posta adresi tanımlı

### Gün 3: Lansman

Kademe kademe:
1. Saat 09:00 — backend deploy (eski sistem birden duruyorsa rollback hazır)
2. Saat 10:00 — Mobil app store'a submit (review 24-48h)
3. Saat 12:00 — Landing page ve sosyal medya duyuruları
4. Gün boyu — Sentry + Grafana izleme

### Gün 4–5: V2 planlaması

Pilot'tan gelen 30+ geri bildirimi grupla:
- **Şimdi çöz (v1.1):** kritik bug, UX showstopper
- **Yakında (v2):** ML kaliteyi artıran, premium feature
- **Sonra (v3):** vizyon, büyük yatırım gereken

İlk v2 önceliği muhtemelen şu üçünden biri olacak:
1. **ML maliyet regresyonu:** kural-tabanlı yetersiz kalacak, gerçek dosyalardan öğren
2. **Plaka/VIN otomatik okuma:** araç markası/modeli → daha doğru fiyat
3. **Sigortacı entegrasyonu API:** CRM'lere webhook + ekspertiz dosyası otomatik üretimi

---

## Pilot Sonrası Beklenebilecek Metrikler

Eğer 4 hafta sonra şunlar elindeyse, v2 yatırımına hazırsın:

- **Teknik:** API uptime ≥%99, p95 latency <3s, ML mAP gerçek dünya verisinde ≥0.50
- **Ürün:** 20+ aktif kullanıcı, NPS ≥30, haftalık iade kullanım %40+
- **İş:** En az 1 ödeme yapan müşteri (B2B veya freemium upgrade)

Bunlar olmadan v2 işsiz beklemeyin — pivot veya kapatma değerlendir.
