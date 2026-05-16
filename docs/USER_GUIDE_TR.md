# Hasarİ — Kullanıcı Rehberi

Hasarİ uygulamasının web, mobil ve masaüstü sürümleri için adım adım kullanım rehberi. Eksperler, hasar danışmanları ve saha çalışanları için yazıldı.

> Bu doküman son kullanıcılara yöneliktir. Geliştirici dokümanları için [README.md](../README.md) dosyasına bakın.

---

## İçindekiler

1. [Başlangıç — Hasarİ nedir, neden kullanmalısın](#1-başlangıç)
2. [Web — kurulum ve ilk inceleme](#2-web)
3. [Mobil — kurulum ve saha kullanımı](#3-mobil)
4. [Masaüstü — kurulum ve toplu işleme](#4-masaüstü)
5. [İlk inceleme — adım adım](#5-i̇lk-i̇nceleme)
6. [Sonuçları anlama](#6-sonuçları-anlama)
7. [Toplu işlem (sadece masaüstü)](#7-toplu-i̇şlem)
8. [Mobil saha kullanım — en iyi pratikler](#8-mobil-saha-kullanım)
9. [Sorun giderme](#9-sorun-giderme)
10. [Destek + iletişim](#10-destek--i̇letişim)

---

## 1. Başlangıç

**Hasarİ nedir?**

Hasarİ, araç fotoğrafından otomatik hasar tespiti yapan bir yapay zeka aracıdır. Bir aracın fotoğrafını yükle; uygulama hangi parçada (ön tampon, kaput, far, vb.) ne tür hasar (göçük, çizik, çatlak…) olduğunu söyler ve tahmini onarım maliyetini Türk Lirası cinsinden verir.

**Kimler için?**

- Sigorta eksperleri ve ön-eksper raporu hazırlayan personel
- Filo yöneticileri (kiralık araç teslim-iadelerinde)
- Galeriler ve oto-ekspertiz noktaları
- Bireysel sürücüler (küçük hasarda eksper masrafına girmeden ön tahmin)

**Hangi hasarları tespit eder?**

| Hasar türü | Türkçe | Tespit kalitesi |
|---|---|---|
| dent | Göçük | Yüksek |
| scratch | Çizik | Yüksek |
| crack | Çatlak | Orta |
| glass_shatter | Cam Kırılması | Yüksek |
| lamp_broken | Far Kırığı | Orta |
| tire_flat | Lastik Patlağı | Düşük (az veri) |

**Hangi parçaları tanır?** 21 parça: tüm tamponlar, kapılar, camlar, farlar/stoplar, kaput, bagaj, aynalar, tekerlek/jant.

**Neye yetmez?**

- Çerçeve hasarı (şasi, longeron) — model bunu görmüyor, mekanik kontrol şart.
- Hava yastığı patlaması, motor hasarı — sadece dış sac/cam hasarı bakar.
- Sigorta talep raporu yerine geçmez — bu sadece **ön rapor**dur. Resmi süreç için yetkili eksper raporu gerekli.

---

## 2. Web

Tarayıcıdan herhangi bir kurulum gerektirmeden kullanabilirsin.

### Sistem gereksinimleri

- Chrome 110+, Edge 110+, Safari 16+, Firefox 110+
- İnternet bağlantısı (fotoğraflar sunucuya yükleniyor)
- Ekran çözünürlüğü en az 1024x768

### Kuruluma gerek yok

1. Tarayıcıdan **https://hasari.app** adresine git.
2. Sağ üst köşeden **Giriş yap** seç (hesap yoksa **Hesap oluştur**).
3. Üst menüden **Yeni inceleme** ile başla.

Web sürümü; ofis ortamında, eksper masasında, müşteri ile birlikte rapor incelemek için idealdir.

---

## 3. Mobil

iOS ve Android için ücretsiz uygulama.

### Sistem gereksinimleri

- **iOS 15+** veya **Android 10+**
- Kamera (arka kamera, en az 8 MP önerilir)
- 100 MB boş depolama alanı
- İnternet bağlantısı (cellular veya Wi-Fi)

### Kurulum

**iOS:**
1. App Store'da "Hasarİ" ara.
2. **Yükle** → açılınca **İzinler** ekranında **Kameraya erişime izin ver** ve **Fotoğraflara erişime izin ver** onayla.

**Android:**
1. Google Play'de "Hasarİ" ara.
2. **Yükle** → açılınca aynı izinleri ver.

### İlk açılış

1. Hoş geldin ekranını geç.
2. Hesabın varsa **Giriş yap**, yoksa **Hesap oluştur**.
3. Ana ekranda büyük **Yeni inceleme** butonu seni karşılar.

Mobil sürüm; sahada, kazanın olduğu yerde, hızlıca fotoğraf çekip rapor almak için tasarlandı.

---

## 4. Masaüstü

Windows, macOS ve Linux için native uygulama. Çoklu fotoğraf, toplu işleme ve klavye kısayolları sunar.

### Sistem gereksinimleri

- **Windows 10/11**, **macOS 12+**, veya **Linux** (Ubuntu 22.04+, Fedora 38+)
- 4 GB RAM
- 200 MB boş disk
- İnternet bağlantısı

### Kurulum

1. **https://hasari.app/download** adresine git.
2. İşletim sistemine uygun yükleyiciyi indir:
   - Windows: `Hasari-Setup.exe`
   - macOS: `Hasari.dmg`
   - Linux: `hasari.AppImage` veya `hasari.deb`
3. Yükleyiciyi çalıştır:
   - **Windows**: Smart Screen "korunmamış uygulama" uyarısı çıkabilir → "Yine de çalıştır".
   - **macOS**: Sağ tık → **Aç** (ilk defa). Apple'ın imzalı geliştirici kontrolünden geçmek için.
   - **Linux**: AppImage için `chmod +x hasari.AppImage && ./hasari.AppImage`.
4. Uygulama açılınca **Ayarlar → API** sekmesinden Backend URL'sini ayarla (varsayılan: `https://hasari-api.onrender.com`). Şirket içi sunucu kullanıyorsan IT'den URL'yi al.
5. **Giriş yap** ekranında hesabınla başla.

Masaüstü sürümü; eksper ofisi, galeri arka ofisi, sigorta operasyon merkezleri için tasarlandı. Toplu işlem (50 fotoğrafa kadar paralel) ve PDF/CSV dışa aktarım özellikleri burada.

---

## 5. İlk inceleme

Üç platformda da temel akış aynıdır. Adım adım inceleyelim.

### 5.1. Fotoğraf çekme/seçme

**İdeal fotoğraf:**
- Aracın **gün ışığında** ya da iyi aydınlatılmış kapalı alanda çekilmiş hali
- Hasarlı parçaya **1-2 metre mesafeden, dik açıdan** çekim
- Parça **net** görünmeli — bulanık fotoğraf modeli yanıltır
- **Birden fazla açı** (en az 2-3) doğruluğu artırır
- Mümkünse aracı **temizle** — toz, çamur, su damlası hasar gibi algılanabilir

**Önerilen çekim setleri:**

| Senaryo | Önerilen fotoğraf sayısı |
|---|---|
| Tek parça, küçük hasar | 1-2 fotoğraf (geniş + yakın) |
| Birden fazla parça hasar | 3-5 fotoğraf (her hasarlı parça için detay) |
| Tüm araç kontrolü | 6-8 fotoğraf (4 cepheden + hasar detayları) |
| Toplu eksperlik (galeri) | 8-12 fotoğraf (4 cephe + 4 köşegen + detaylar) |

**Mobilde:**
- Ana ekrandan **Yeni İnceleme** → **Fotoğraf çek** veya **Galeriden seç**.
- Kamera açıldığında **flaş otomatik**'i kullan. Cam ve metal yüzeyde flaş yansıtması olursa flaşı kapat ve tekrar çek.
- Her fotoğraftan sonra **Önizleme** ekranında **Tut** veya **Yenile**.

**Web/Masaüstüde:**
- **Sürükle bırak** veya **Dosya seç** ile JPG/PNG/WebP yükle (her dosya max 12 MB).
- Birden fazla dosyayı Ctrl+tıklayarak veya hepsini seçerek aynı anda ekle.

### 5.2. İşlem modu seçimi

İki mod var:

| Mod | Kullanım | Limit | Süre |
|---|---|---|---|
| **Hızlı (sync)** | 1-5 fotoğraf, anlık sonuç beklerken | 5 fotoğraf | 5-15 saniye |
| **Detaylı (async)** | 5-20 fotoğraf, arka planda işle | 20 fotoğraf | 30-90 saniye |

Genelde 3-5 fotoğraf çekiyorsan **Hızlı** mod yeterli. Toplu inceleme için **Detaylı** modu kullan; pencere kapansa da arka planda devam eder ve bildirim gelir.

### 5.3. İncelemeyi başlat

**Yeni inceleme** ekranında:

1. Fotoğrafları yüklediğinden emin ol.
2. Modu seç.
3. **İncelemeyi başlat** butonuna bas.
4. İlerleme çubuğu görünür:
   - "Fotoğraflar yükleniyor… (2/5)"
   - "Sıraya alındı, başlatılıyor…"
   - "Hasar tespiti yapılıyor…"
   - "Araç parçaları algılanıyor…"
   - "Şiddet tahmin ediliyor…"
   - "Maliyet hesaplanıyor…"
   - "Sonuçlar hazırlanıyor…"
5. Sonuç ekranı otomatik açılır.

> İşlem 3 dakikadan uzun sürerse bir aksaklık var. **İptal et** ve [sorun giderme](#9-sorun-giderme) bölümüne bak.

---

## 6. Sonuçları anlama

Sonuç ekranı dört sekmeden oluşur: **Özet**, **Parçalar**, **Hasarlar**, **Görselleştirme**.

### 6.1. Özet sekmesi

Üstte tek bakışta görmek istediğin sayılar:

- **Hasarlı parça**: Modelin hasar tespit ettiği parça sayısı (örn. 3).
- **Hasarsız parça**: Tespit edilen ama hasarsız olduğu işaretlenen parça sayısı (örn. 4).
- **Toplam hasar**: Tüm parçalardaki ayrı hasar sayısı (1 parçada 2 hasar olabilir).
- **Tahmini toplam maliyet**: Lira cinsinden aralık, örn. ₺6.800 - ₺14.500.
- **Genel şiddet**: En ağır hasarın şiddeti (Hafif/Orta/Ağır).
- **Tamir önerisi**: Sistemin önerdiği işlem — `Tamir + boya gerekli`, `Sadece boya`, `Parça değişimi öneriliyor` gibi.

### 6.2. Hasar türleri

Sistemin tanıdığı 6 ana hasar türü:

| Sembol | Türkçe | Açıklama |
|---|---|---|
| ![](https://via.placeholder.com/15/F59E0B/000?text=+) | **Göçük** (dent) | Sac yüzeyde içe çökme; çapa göre maliyet değişir |
| ![](https://via.placeholder.com/15/FB923C/000?text=+) | **Çizik** (scratch) | Boya hasarı, sac sağlam; cila/boya yeterli |
| ![](https://via.placeholder.com/15/EF4444/000?text=+) | **Çatlak** (crack) | Plastik veya tampondaki kırık; yapıştırma veya parça değişimi |
| ![](https://via.placeholder.com/15/A855F7/000?text=+) | **Cam Kırılması** (glass_shatter) | Ön cam, yan cam, arka cam; ya tamir ya değişim |
| ![](https://via.placeholder.com/15/EC4899/000?text=+) | **Far Kırığı** (lamp_broken) | Far, stop veya sis ışığı camı; parça değişimi gerekir |
| ![](https://via.placeholder.com/15/64748B/000?text=+) | **Lastik Patlağı** (tire_flat) | Görünür patlak/sönüklük; lastik değişimi |

### 6.3. Şiddet seviyeleri

Her hasara üç seviyeden biri atanır:

- **Hafif**: Yüzeysel, sac sağlam. Cila veya boya yeterli olabilir.
- **Orta**: Sac eğilmiş veya çatlak küçük. Tamir + boya.
- **Ağır**: Belirgin deformasyon veya kırılma. Parça değişimi olası.

> ⚠ Şiddet modeli **az veriyle** eğitildi (30 epoch); özellikle "Orta-Ağır" arasında zaman zaman karışıklık var. Şüpheli durumda görsel kontrolle doğrula.

### 6.4. Parçalar sekmesi

21 parçanın tamamı listelenir. Her parça için:

- **Hasarsız parçalar** üst grup — yeşil tikle gösterilir.
- **Hasarlı parçalar** alt grup — her parçanın altında o parçadaki tüm hasarlar (tür, şiddet, maliyet) sıralanır.

Parça kartına tıklayınca o parçanın detay görünümü açılır.

### 6.5. Hasarlar sekmesi

Aynı veri ama hasar-merkezli bakış. Tüm tespit edilen hasarları **şiddet sırasına göre** veya **maliyet sırasına göre** sıralayabilirsin.

### 6.6. Görselleştirme sekmesi

Üç farklı görsel:

- **İşaretli (annotated)**: Orijinal fotoğraf + tüm hasar bölgeleri renkli maskelerle.
- **Parçalar**: Sadece parça maskelerini gösterir — sistemin neyi neresi olarak gördüğünü anlamak için.
- **Hasarlar**: Sadece hasar maskelerini gösterir.

Görseli sağ tıklayıp **Görseli indir** ile PNG olarak kaydedebilirsin (rapor için kullanışlı).

### 6.7. Maliyet aralığı nasıl yorumlanır?

Sistem maliyet aralığı verir, tek bir rakam değil. Örnek: **₺2.500 - ₺5.500**.

- **Alt sınır**: Aftermarket parça + standart işçilik (ekonomik servis)
- **Üst sınır**: OEM (orijinal) parça + yetkili servis işçiliği
- **Tahmini orta nokta**: İkisinin ortalaması, hızlı karar için iyi bir referans.

> Bu rakamlar **lokal Türkiye fiyat tabanına** göre Mart 2026'da kalibre edildi. Kur dalgalanması ve bölgesel farklar olur — saha pratiğine göre ±%20 sapma normaldir.

### 6.8. Rapor paylaşma

- **PDF olarak indir**: Müşteriye e-postayla göndermek için.
- **JSON olarak indir**: Başka sistemlere aktarmak için (sigorta yazılımı entegrasyonu vb.).
- **Bağlantıyı paylaş**: Açık bir URL üretir — alıcının hesabı varsa görüntüleyebilir.

---

## 7. Toplu işlem

> Bu özellik sadece **masaüstü** sürümünde.

Galeri stoğu, kiralık filo iadeleri, sigorta acentesi günlük dosyaları için 50 fotoğrafa kadar bir seferde işleyebilirsin.

### Akış

1. Sol menüden **Toplu işleme** sekmesi.
2. **Klasör seç** ile bir klasördeki tüm görüntüleri ya da **Dosya seç** ile tek tek ekle.
3. Eklenenler "Sıra" listesinde görünür — her satırda küçük önizleme, dosya adı, durum (Sırada → Yükleniyor → İşleniyor → Tamamlandı/Başarısız).
4. **Toplu başlat** → uygulama paralel 3 dosyayı işler, sıradakileri tamamlandıkça başlatır.
5. İlerleme çubuğu üstte: "Tamamlanan / Toplam".
6. Tamamlandığında **CSV olarak dışa aktar** veya **Tüm raporları PDF olarak indir**.

### Çalışırken yapabileceklerin

- **Duraklat / Devam et**: Sırayı geçici durdur (zaten işlenmekte olanlar bitirilir).
- **Sırayı temizle**: Henüz başlamamış olanları çıkar (tamamlananlar kalır).
- **Başarısızları yeniden dene**: Sadece "Başarısız" olanları tekrar kuyruğa al.

### CSV çıktısı

| Sütun | İçerik |
|---|---|
| `inspection_id` | UUID |
| `file_name` | Yüklenen dosyanın adı |
| `damaged_parts_count` | Hasarlı parça sayısı |
| `total_damage_count` | Toplam hasar |
| `total_cost_min_tl`, `total_cost_max_tl` | Maliyet aralığı |
| `overall_severity` | hafif / orta / agir |
| `repair_recommendation` | Sistemin önerisi |
| `processed_at` | Tarih-saat |
| `status` | completed / failed |

---

## 8. Mobil saha kullanım

Saha çekimi farklıdır. Aşağıdaki ipuçları doğruluğu belirgin artırır.

### Işık koşulları

| Koşul | Yapılacak |
|---|---|
| **Gün ışığı, açık hava** | İdeal. Gölgeye gerek yok. |
| **Bulutlu, dağınık ışık** | İdeal. Yansıma yok, detay net. |
| **Doğrudan güneş, parlama** | Aracı yarı-gölgeye çek veya kendi gölgenle parça üstüne gölge düşür. |
| **Garaj, loş ortam** | Flaş ON, ancak metal/cam üzerinde yansımayı önlemek için 45 derece açıdan çek. |
| **Gece** | Önerilmez — el feneri ile yan-aydınlatma yap; yine de hata oranı artar. |

### Açı ve mesafe

- **Mesafe**: 1-2 metre. 50 cm'den yakın çekim distorsiyona yol açar.
- **Açı**: Hasarlı yüzeye **dik** (90°). Eğik açıda perspektif bozulur.
- **Yükseklik**: Hasarın merkez yüksekliğinden çek — alttan/üstten çekme.

### Çoklu açı pratiği

Aynı hasarı 2 farklı açıdan çekersen model emin olur:

1. **Dik açı, yakın** — hasarın tam karşısından, 1 m mesafede.
2. **30-45° açı** — yan-perspektiften, parçanın bağlamını gösterir.

### Saha checklist

Telefondan inceleme başlatmadan önce:

- [ ] Lens temiz mi? Pamuklu mendille sil.
- [ ] Pil ≥ %30 mu? (Yükleme uzun sürerse koparmasın.)
- [ ] İnternet sinyali iyi mi? Wi-Fi varsa ona bağlan.
- [ ] Hasarlı bölge fotoğrafta net mi? Önizlemede yakınlaştır, bulanıksa tekrar çek.
- [ ] Plaka veya VIN görünüyor mu? KVKK gereği bunları rapora dahil etme; çekim açısını ona göre ayarla.

---

## 9. Sorun giderme

### "Fotoğrafta araç algılanamadı"

**Sebep**: Model fotoğrafta net bir araç bulamadı.
**Çözüm**:
- Aracın çoğunluğu kadrajda mı? En az %30'u görünmeli.
- Çok yakın (motor kapağı çekimi gibi) veya çok uzak (otoparktaki 20 araç) olmamalı.
- Aydınlatma yeterli mi? Loş fotoğrafta tekrar dene.

### "Görüntü çok bulanık"

**Sebep**: Fotoğraf hareketten veya odaklanmamadan bulanık.
**Çözüm**: Telefonu sabitle, ekrana dokunup hasarı odakla, sonra çek. Mümkünse her iki elinle tut.

### "Yükleme başarısız"

**Sebep**: İnternet kesintisi veya dosya çok büyük.
**Çözüm**:
- Wi-Fi'a bağlan ve tekrar dene.
- Fotoğraf 12 MB'ı geçiyor mu? Mobilde "yüksek kalite" yerine "yüksek verim" çekim ayarını kullan.

### Sonuçlar yanlış görünüyor

**Sebep**: Model bazı parça/hasarları yanlış sınıflandırmış olabilir.
**Çözüm**:
- **Görselleştirme** sekmesinden "İşaretli" görseli aç. Modelin neyi nereden gördüğünü gör.
- Belirgin hata varsa **Sorun bildir** ile bize gönder — model bir sonraki sürümde iyileşir.
- Eksper yargın model çıktısına üstün gelir; nihai karar senin.

### "Sunucuya ulaşılamıyor"

**Sebep**: Backend kapalı, internet yok veya yanlış URL.
**Çözüm**:
- İnternet bağlantısını kontrol et.
- Masaüstü sürümünde **Ayarlar → API → Bağlantıyı test et**.
- 5 dk bekleyip tekrar dene; sunucu yeniden başlatılıyor olabilir.

### "Oturum süresi doldu"

**Sebep**: 7 günden uzun giriş yapmadın, refresh token süresi geçti.
**Çözüm**: Yeniden giriş yap. Sık kullanıyorsan **Beni hatırla**'yı işaretle.

### Mobil uygulama açılırken çöküyor

**Çözüm**:
1. Uygulamayı tamamen kapat (görev yöneticisinden).
2. Telefonu yeniden başlat.
3. Uygulama güncellemesi var mı, App Store/Play Store'dan kontrol et.
4. Hâlâ çöküyorsa: uygulamayı kaldır + yeniden yükle (verilerin sunucuda, kaybolmaz).

### Masaüstü "ML modeli yüklenmedi" diyor

**Sebep**: Backend modelleri yükleyemedi.
**Çözüm**: Bekle (genelde 30-60 saniye içinde toparlar). 5 dk geçince hala "yüklenmedi" diyorsa destekle iletişime geç.

---

## 10. Destek + iletişim

| Konu | Nasıl |
|---|---|
| **Genel destek** | weblineet@gmail.com |
| **Hata bildirimi** | Uygulamada **Sorun bildir** veya GitHub Issues |
| **Pilot kullanıcı geri bildirim** | Aylık toplantı + Slack kanalı (pilot katılımcılar) |
| **Acil teknik destek** | (pilot anlaşmasında belirtilen telefon hattı) |

---

## Sürüm notları

- **v0.1 (MVP)** — şu an. TR/EN UI, web + mobil + masaüstü, 3 modelli pipeline, JWT auth.
- **v0.2 (planlanan)** — mobil on-device ön-kontrol (offline çalışır), maliyet motoru ML regresyonu, Türkçe araç markası fine-tune.
- **v1.0 (uzun vade)** — VIN/plaka anonimleştirme, fraud detection, B2B partner panosu.

Sürümler arası geçişte verilerin kaybolmaz; sadece UI yenilenir.
