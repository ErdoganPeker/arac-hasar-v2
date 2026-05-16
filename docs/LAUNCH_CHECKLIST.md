# Lansman Kontrol Listesi

MVP lansman günü öncesi her satırı kontrol et. Hepsinde **YEŞİL** olmadan canlıya çıkma.

Tarih: __________
Sorumlu: __________

---

## 🔧 Teknik Hazırlık

### Backend

- [ ] API tüm endpoint'leri çalışıyor (`/health` 200, `/api/v1/inspect?mode=async` 202)
- [ ] Production ortamında deploy edildi (AWS/Azure/GCP)
- [ ] HTTPS sertifikası geçerli, www ve apex yönlendirme doğru
- [ ] Environment variable'ları production değerlerle dolduruldu (.env.production)
- [ ] Database backup günlük otomatik
- [ ] Redis ve S3 erişimleri doğru
- [ ] CORS origin'leri production domainine kısıtlandı
- [ ] Rate limiting aktif (en az 100 req/dk per API key)
- [ ] Webhook signature doğrulaması (opsiyonel ama önerilir)

### ML Modeli

- [ ] Production modeli `models/` altında, doğru sürüm
- [ ] GPU instance üzerinde inference < 2s (p95)
- [ ] Regression test suite ≥%85 pass
- [ ] Soğuk başlangıç warm-up tamamlanıyor (60s içinde)
- [ ] Sentry'de son 24 saatte 0 kritik hata

### Mobil

- [ ] iOS TestFlight'ta canlı (review onaylı)
- [ ] Android Google Play Internal Testing'de canlı
- [ ] Production API URL kullanılıyor (staging değil)
- [ ] App icon, splash screen, app store ekran görüntüleri hazır
- [ ] App store açıklama metinleri Türkçe + İngilizce
- [ ] Sentry sürüm release tag bağlı
- [ ] Crash-free user oranı son 24h ≥%99

---

## 🛡️ Güvenlik

- [ ] API key'ler environment'tan okunuyor, kod içinde değil
- [ ] Database credential'ları rotated, eski rapora yok
- [ ] HTTPS-only, HTTP-to-HTTPS redirect var
- [ ] S3 bucket policy: public-read sadece resimler için
- [ ] Plaka/VIN anonimleştirme aktif
- [ ] CORS sadece kendi domainlere açık (`*` yasak)
- [ ] Penetration test temel kontrolleri (OWASP top 10) yapıldı
- [ ] Secret scanning CI'da aktif

---

## ⚖️ Yasal / KVKK

- [ ] KVKK aydınlatma metni landing page'de + uygulamada
- [ ] Kullanıcıdan açık rıza alınıyor (görüntü işleme, AB sunucusu)
- [ ] Veri silme/erişim talep süreci tanımlı (kvkk@domain)
- [ ] Kullanım şartları + gizlilik politikası yayında
- [ ] Şirket kuruldu (ya da bireysel girişimci durumu net)
- [ ] Faturalama altyapısı var (B2B için)

---

## 📊 İzleme

- [ ] Sentry: backend + frontend + mobil 3'ü de bağlı
- [ ] Grafana dashboard üretim metriklerini gösteriyor
- [ ] Slack/Discord'a uyarı entegrasyonu (kritik hata > webhook)
- [ ] Uptime monitoring (UptimeRobot, BetterStack, vs.)
- [ ] Database slow query log aktif
- [ ] Disk/CPU/RAM alarmları tanımlı (%80 threshold)
- [ ] Günlük log rotation, 30 gün retention

---

## 📞 Müşteri Hizmetleri

- [ ] destek@domain e-posta canlı
- [ ] Yanıt SLA: 24 saat (ilk 30 gün), sonra 48 saat
- [ ] Sık sorulan sorular sayfası (FAQ)
- [ ] WhatsApp business veya canlı sohbet (opsiyonel ama önerilir)
- [ ] Bug raporu için GitHub issue veya Linear projesi kurulu

---

## 💼 İş Tarafı

- [ ] Landing page (domain.com) yayında, mobil-responsive
- [ ] Fiyatlandırma sayfası net (B2C ücretsiz mi, B2B abonelik mi)
- [ ] Demo videosu (60 saniye) ana sayfada
- [ ] Pilot kullanıcıların onayı ile case study/testimonial bölümü
- [ ] Sosyal medya hesapları aktif (LinkedIn, Twitter/X, Instagram)
- [ ] İlk PR / blog yazısı hazır
- [ ] Etiket ve domain sahipliği vekaletsiz (domain.com.tr için TR-NIC işlemleri)

---

## 📈 Lansman Sonrası İlk 48 Saat İzleme Planı

**Saat 0 (lansman anı):**
- API'yi public et
- Lansman tweet'i / LinkedIn post'u
- Sentry + Grafana açık tut

**Saat +1:**
- Health check her 5 dakikada bir
- İlk gerçek kullanıcı kim, dene

**Saat +6:**
- Aktif kullanıcı sayısı, hata oranı incele
- Sosyal medya yorumlarına yanıt ver

**Saat +24:**
- Günlük rapor: kayıt, inceleme, hata, yanıt süresi
- Kritik sorunlar varsa hotfix

**Saat +48:**
- Haftalık planlamayı güncelle
- v1.1 backlog'una pilot'tan gelen geri bildirimleri ekle

---

## 🚨 Rollback Planı

Eğer kritik bir sorun çıkarsa:

1. **Backend rollback:** Önceki Docker image tag'ine geri dön (5 dakika)
2. **Mobil rollback:** Yeni sürüm bekleyebilir, mevcut store sürümü çalışmaya devam eder
3. **Veritabanı:** Schema değişikliği geri alınabilir mi? (rollback migration test edildi mi)
4. **DNS:** Maintenance page'e geçici yönlendirme (varsa)

Bu listeyi 1 hafta öncesinden gözden geçir, son hafta tüm satırları yeşillemek için adımları sıralı planla.
