# UX Multi-Foto Inspection Flow — Heuristic Audit

**Kapsam:** `apps/web/` üzerinden çok-fotoğraflı (`async`, 6-20 görsel) inceleme akışının uçtan uca UX boşluk analizi.

**Yöntem:** Heuristic değerlendirme (Nielsen 10 + Mobil B2C bağlamı). Statik kod incelemesi — runtime test yok. Senaryo: kullanıcı 12 foto yükledi, backend tamamladı, ama frontend "internet yok" gösterdi + history'de thumbnail yok + bazı sonuçlar "hasarsız" göründü.

**İncelenen dosyalar:**
- `apps/web/app/inspect/page.tsx` (anon upload — single page)
- `apps/web/app/(app)/inspect/new/page.tsx` (auth upload, sürüm farkı: progress bar var)
- `apps/web/app/results/[id]/page.tsx`
- `apps/web/app/history/page.tsx`
- `apps/web/lib/use-inspection-polling.ts`
- `apps/web/lib/uploaded-previews.ts`
- `packages/ui/src/components/UploadDropzone.tsx` + `MultiImageThumbnailGrid.tsx`
- `apps/web/messages/tr.json`

**Şiddet skalası:** 1 (kozmetik) ↔ 5 (görev tamamlanmıyor).

---

## 1. Foto Seçim Aşaması (`/inspect` ve `/inspect/new`)

### Bulgu M1.1 — Mode badge eşik anında görünür ama "neden değişti" açıklanmıyor — Şiddet 3
**Konum:** `app/inspect/page.tsx` satır 53-58, `effectiveMode` türetimi.
**Gözlem:** Kullanıcı 5 fotoyu geçince `sync` butonu sessizce disable oluyor (`showSyncOption = files.length <= MAX_SYNC_FILES`). UI'da `effectiveMode === 'async'` olarak otomatik zorlanıyor ama kullanıcı bunun **neden** olduğunu anlamıyor — "Hızlı işle" mod kartı yarı saydam (`opacity-50`) ve tıklanamaz; herhangi bir tooltip / yardım metni yok.
**12 foto seçen kullanıcı için kritik:** Modu seçtiğini sandığı ekranda aslında seçenek otomatik kilitlendi. "Neden async'e zorlandım?" sorusu cevapsız.
**Öneri:** Async kartının altına şu uyarı çıksın (yalnızca files.length > 5 iken görünür):
> "5+ fotoğraf seçtin — sonuç ~10 sn'de hazır olacak. Hızlı işle bu kadar fotoğrafla mümkün değil."

### Bulgu M1.2 — "Tahmini süre" hiçbir aşamada gösterilmiyor — Şiddet 3
**Konum:** `app/inspect/page.tsx` mode kartları (satır 150-167), submit butonu (185-202).
**Gözlem:** `tr.json` içinde `inspect.estimatedTimeRemaining` ("Tahmini kalan süre: {seconds} sn") çevirisi tanımlı — **hiçbir bileşen kullanmıyor**. `modeAsyncDesc` "Arka planda işlenir. Çok sayıda görüntü için uygun." diyor ama somut bir süre vermiyor. 12 foto için kullanıcı "10 sn mi, 5 dk mı?" bilmiyor.
**Öneri:** Mode kartlarına dinamik süre badge'i: `n × 0.8sn + 2sn` formülünden (model+kuyruk) `~12 sn` gibi. Submit butonuna da: "İncelemeyi başlat • ~12 sn sürer".

### Bulgu M1.3 — Submit butonu sırasında file count değişimi gösterilmiyor — Şiddet 2
**Konum:** `app/inspect/page.tsx` satır 129.
**Gözlem:** `filesSelected` mesajı "{count} dosya seçildi" — sade. Ancak `MAX_ASYNC_FILES = 20` üst sınırı kullanıcıya gösterilmiyor; UploadDropzone'un internal `maxFiles` validasyonu kart içinde gizli (`En fazla 20 dosya yükleyebilirsin.`). Kullanıcı 18 foto seçtiğinde "2 fotoğraf daha ekleyebilirim" sinyalini almıyor.
**Öneri:** Sayaç formatı: "12 / 20 dosya seçildi" + ilerleme çubuğu (görsel).

### Bulgu M1.4 — Dropzone hint metni hardcode TR (i18n bypass) — Şiddet 2
**Konum:** `packages/ui/src/components/UploadDropzone.tsx` satır 22, 89.
**Gözlem:** `"Görüntüleri sürükle bırak veya tıkla"` ve `hint="JPG, PNG, WEBP — maks. 12MB / dosya"` doğrudan kod içinde Türkçe. `tr.json` içinde `inspect.dropHere`, `dragOrClick`, `supportedFormats` çevirileri var ama UploadDropzone props ile değil sabit string ile çalışıyor.
**Etkisi multi-foto akışına:** EN locale'de geçince kullanıcı seçim hatası yapma riski (yanlış format) + brand güveni düşer.

---

## 2. Yükleme Sırası

### Bulgu M2.1 — Anonim akışta progress bar yok — Şiddet 4
**Konum:** `app/inspect/page.tsx` satır 65 `createInspection(files, { mode: effectiveMode })`.
**Gözlem:** `createInspection` `onUploadProgress` callback'i destekliyor (`lib/api.ts` satır 346-350) ama anonim sayfa bu callback'i hiç wire etmiyor. 12 × 5 MB = 60 MB yüklerken kullanıcı yalnızca "Yükleniyor…" spinner görüyor. 4G bağlantıda bu 30-90 sn boyunca **donmuş** algılanıyor.
**Auth versiyonu** (`(app)/inspect/new`) progress bar gösteriyor — paritenin olmaması anonim demo'da terk oranını ciddi yükseltir.
**Öneri:** `onUploadProgress` ekle + yüzde + bayt cinsinden bilgi:
> "Fotoğraflar yükleniyor… (4/12 dosya, %33)"
**`tr.json` `inspect.progress.uploading` zaten mevcut.**

### Bulgu M2.2 — "İptal" yok — Şiddet 3
**Konum:** `app/inspect/page.tsx` submit handler (satır 60-83).
**Gözlem:** `createInspection` `signal: AbortSignal` parametresi alıyor (api.ts satır 301) — anonim sayfa AbortController kullanmıyor. 12 fotoyu yükledikten sonra "bu yanlış seti seçtim, iptal" demek istersem yapamam. Tek çare sekmeyi kapatmak.
**Auth sayfasında da `cancelInspection` çevirisi `tr.json`'da hazır ama wire değil.**
**Öneri:** Yükleme sırasında submit butonu disabled olduğunda yerine "İptal et" butonu konsun, AbortController'ı tetiklesin.

### Bulgu M2.3 — Foto başına ilerleme yok, toplu ilerleme bile yok — Şiddet 3
**Konum:** Aynı yer.
**Gözlem:** Axios `onUploadProgress` toplam byte ilerlemesi verir — şu an kullanılmıyor bile. Dosya başına ilerleme yapısal olarak mümkün değil (tek multipart POST). Ancak hangi dosyanın gönderildiğini estimate eden bir "dosya {n}/{total}" hesabı kolay: `loaded / file.avgSize`.
**Öneri:** En azından toplu yüzde + "12 fotoğraftan ~5'i yüklendi" gibi türetilmiş metin.

### Bulgu M2.4 — `stashUploadedPreviews` yükleme bitmeden çağrılmıyor — Şiddet 2
**Konum:** `app/inspect/page.tsx` satır 66, await sırası.
**Gözlem:** `stashUploadedPreviews` HTTP POST tamamlandıktan sonra çalışıyor (canvas resize + base64). 12 foto için bu adım da 1-3 sn alabilir ve **kullanıcı bu sırada hiçbir feedback görmüyor** — `submitting` true kalıyor, "Yükleniyor…" yazısı sürüyor (yanlış, aslında upload bitti).
**Öneri:** Yükleme bittiğinde label "İnceleme başlatıldı, yönlendiriliyorsun…" olarak değişsin.

---

## 3. Polling / Sonuç Bekleme (`/results/[id]`)

### Bulgu M3.1 — "İnternet bağlantın yok" yanıltıcı mesaj (RAPORLANAN ŞİKAYETLE BİREBİR EŞLEŞME) — Şiddet 5
**Konum:** `lib/use-inspection-polling.ts` satır 170-182 + `tr.json` `errors.network.offline`.
**Gözlem:** Polling sırasında 5xx/network hata olduğunda mesaj `tNetwork('offline')` = **"İnternet bağlantın yok"** olarak set ediliyor. Ama gerçek senaryolar:
1. Backend tamamladı ama 401 → refresh interceptor → kısa pencere içinde 5xx blip
2. Render free tier cold start (sırada bekliyor)
3. CORS preflight failure
4. Kullanıcı **diğer** sekmede internet kullanıyor (bağlantı aktif), ML servisi yavaş

Bu durumların hiçbiri "internet bağlantın yok" değil. Backend log'una bakan dev rahatlıkla "tamamlandı" görür ama kullanıcı "router'ım mı kapandı?" diye düşünür → güven kaybı.
**Öneri (P0):** Network kind'ını ikiye böl: gerçek `navigator.onLine === false` durumunda "İnternet bağlantın yok"; aksi her şeyde **"Sunucudan yanıt alamıyoruz — inceleme arka planda devam ediyor olabilir."** + `checkAgain` butonu.

### Bulgu M3.2 — PendingState her zaman aynı görünüyor — Şiddet 3
**Konum:** `app/results/[id]/page.tsx` satır 307-334.
**Gözlem:** 12 fotoluk async batch 30-90 sn sürebilir. `PendingState` yalnızca "İşleniyor…" + spinner gösteriyor. `attempts > 1` iken "Durum kontrol sayısı: 5" ekleniyor — bu **teknik metrik**, kullanıcıya değer katmıyor (aksine endişe). `tr.json` `inspect.progress.{detectingParts,detectingDamages,calculatingCost,almostDone}` mevcut ama hiç kullanılmıyor.
**Öneri:**
- Sahte ilerleme rotasyonu (her 4-5 sn'de bir metin değişimi):
  - 0-5 sn: "Fotoğraflar sunucuya iletildi"
  - 5-15 sn: "Araç parçaları algılanıyor…"
  - 15-30 sn: "Hasarlar tespit ediliyor…"
  - 30-50 sn: "Maliyet hesaplanıyor…"
  - 50+ sn: "Neredeyse bitti…"
- `pollAttempts` çevirisini gizle (debug-only).
- Tahmini geri sayım: "~ 12 sn kaldı" (file count'tan türetilmiş).

### Bulgu M3.3 — `timedOut` ekranı yanıltıcı: "İşleniyor…" + errorGeneric — Şiddet 3
**Konum:** `app/results/[id]/page.tsx` satır 80-95.
**Gözlem:** 180 sn dolunca `timedOut=true` → `EmptyState` başlık "İşleniyor", açıklama `errorGeneric` ("Bir hata oluştu…"). Çelişkili — hem "işleniyor" hem "hata" diyor. CTA "Sayfayı yenile" — refresh sonrası polling yeniden başlıyor, bu doğru ama frame yanlış.
**Öneri:** Yeni mesaj key'i:
> Title: "Sonuç hâlâ hazırlanıyor"
> Desc: "İncelemen normalden uzun sürdü. Geçmiş'ten birkaç dakika içinde görebilirsin veya yeniden kontrol et."
> CTA 1: "Tekrar kontrol et" (sayfayı yenile)
> CTA 2: "Geçmişe git" (`/history`)

### Bulgu M3.4 — `paused` state UI'da görünmüyor — Şiddet 3
**Konum:** `lib/use-inspection-polling.ts` satır 8-21 (`paused` field) vs `app/results/[id]/page.tsx`.
**Gözlem:** Hook 8 ardışık hatadan sonra `paused: true` set ediyor + yorumda "UI shows a 'check again' button" yazılı **ama results sayfası `paused` field'ını hiç okumuyor**. Bunun yerine `error` mesajı görünür kalıyor (= "İnternet bağlantın yok"). 12 fotolu inspection'da Render cold start = 60 sn = 8 polling failure birikebilir → kullanıcı hâlâ offline yazısı görüyor.
**`tr.json` `inspect.result.pollPausedTitle/Desc/checkAgain` mevcut ama bağlanmamış.**
**Öneri:** `paused === true` iken `<PendingState>` yerine `<PausedState>` render et:
> "Sonuç hazırlanıyor — sunucudan birkaç yanıt alamadık ama inceleme arka planda devam ediyor."
> CTA: "Tekrar kontrol et" (= `retry()`).

### Bulgu M3.5 — "Arka planda devam ediyor" alternatifi yok — Şiddet 2
**Konum:** Tüm result sayfası.
**Gözlem:** Kullanıcı 12 foto yüklediği için 60+ sn bekliyor. Sayfada "Sekmeyi kapat, sonucu /history'den göreceksin" gibi bir çıkış yolu yok. Mobile kullanıcı ekranı kilitlerse polling kesilir; uyandığında polling yeniden başlar ama bunu bilmiyor.
**Öneri:** Polling 30 sn'yi geçince footer'a bilgi: "Beklemek istemezsen Geçmiş'ten daha sonra görebilirsin →".

---

## 4. Sonuç Ekranı — Multi-Foto Özel

### Bulgu M4.1 — Aggregate sonuç tek görsel üzerinden gösteriliyor — Şiddet 4
**Konum:** `app/results/[id]/page.tsx` `ResultsView`, satır 136-139:
```
const annotatedUrl = result.visualization_urls?.annotated ?? result.image.url ?? '';
```
**Gözlem:** Backend 12 fotodan aggregate üretiyor (16 toplam hasar, 5 hasarlı parça, 10 atanmamış). UI **tek bir `annotatedUrl`** seçip onu büyük tab'da gösteriyor. 12 fotonun her biri ayrı bir bakış açısı olabilir — kullanıcı:
- "Hangi açıdan çekilen fotoğrafta sol kapı hasarı bulundu?" cevabını alamıyor
- "10 atanmamış hasar nerede?" sorusu için referans noktası yok
- Sadece 1 fotonun annotation'ını görüyor → "Diğer 11 foto işlendi mi yoksa atıldı mı?" şüphesi

`MultiImageThumbnailGrid` bileşeni **paket içinde mevcut** — bu sayfada kullanılmıyor.
**Öneri (P0):**
- `result.images: []` array varsa `MultiImageThumbnailGrid` ile 12 thumbnail göster.
- Her thumbnail'a o foto için hasar sayısı badge'i (`badge={n}`).
- Tıklayınca ana viewport o foto + annotation'a geç.
- Header: "12 fotoğraf işlendi — agregat rapor aşağıda".

### Bulgu M4.2 — Atanmamış hasarların "10/16" oranı sessizce gizleniyor — Şiddet 4
**Konum:** `app/results/[id]/page.tsx` satır 191-205 (`unassigned_damages` section).
**Gözlem:** Section ancak `unassigned_damages.length > 0` iken render oluyor — gri/beyaz kart, görsel ağırlık düşük (`border-slate-200 bg-white`). 16 hasardan 10'u (= %62.5) atanmamışsa bu **dominant sinyal** ama UI'da kenara itilmiş. Header'da büyük rakam görünmüyor; sadece DamageBadge listesi var.
`tr.json` `unassignedDamagesAlertTitle` ("Parçaya atanamayan hasar tespit edildi") + `mixedResultTitle` ({damagedParts} hasarlı parça + {unassigned} atanamayan hasar) zaten yazılı — bağlanmamış.
**Öneri:**
- Atanmamış oran > %30 ise sayfanın üstünde uyarı banner'ı (amber):
  > "16 hasarın 10'u belirli bir parçayla eşlenemedi — fotoğraf çekimi açısı yetersiz olabilir."
- Tekrar foto yükle CTA'sı + tip linki.

### Bulgu M4.3 — "Hasarsız" yanılgısı (RAPORLANAN ŞİKAYET) — Şiddet 5
**Konum:** `app/results/[id]/page.tsx` summary section + `tr.json` `inspect.result.noDamage`.
**Gözlem:** Senaryo: 12 foto, backend `parts=[]` (model parça-merkezli atama yapamamış) ama `unassigned_damages=[16 adet]`. UI:
- `result.parts` boş → `PartList` boş → "hasarsız parça" izlenimi
- `result.summary.most_severe_level_tr` muhtemelen "Bilinmiyor" veya boş
- Cost tahmini muhtemelen düşük/sıfır (parça başına hesaplanıyorsa)
- Visual'da "Tebrikler, aracın temiz görünüyor." (noDamageSubtitle) çıkma riski

Kullanıcı **16 hasarı olan bir aracı "hasarsız" olarak okuyor**. Bu güven kaybının yanı sıra sigorta/satım kararlarında yanlış aksiyon riski (etik problem).
**Öneri (P0):**
- "Hasarsız" verdicti ancak `allDamages.length === 0 && unassigned_damages.length === 0 && multi_part_damages.length === 0` iken yazılsın.
- Aksi halde: "Hasar tespit edildi ama tam atanamadı — manuel inceleme öneriyoruz."
- `CostDisplay` aynı koşulu uygulasın (atanmamış hasar varsa "Tahmin yapılamadı" + retake CTA).

### Bulgu M4.4 — Kullanıcının yüklediği orijinal fotolar gösterilmiyor — Şiddet 3
**Konum:** `lib/uploaded-previews.ts` + `app/results/[id]/page.tsx`.
**Gözlem:** `stashUploadedPreviews` kullanıcının fotolarını sessionStorage'a base64 olarak yazıyor (2 MB cap). `getUploadedPreviews` ihraç edilmiş **ama results sayfasında import edilmiyor**. Backend 1 görsel döndürüyorsa kullanıcı "12 foto yükledim, sadece 1'i mi göründü?" diye şüpheleniyor.
**`tr.json` `uploadedPreviewTitle` ("Yüklediğin görseller") + `uploadedPreviewDesc` mevcut.**
**Öneri:** Sayfa altında "Yüklediğin görseller (12)" accordion: `MultiImageThumbnailGrid` + sessionStorage preview'leri. En azından kullanıcı "fotolarım kayboldu" hissi yaşamaz.

### Bulgu M4.5 — Çoklu-parça hasarları (`multi_part_damages`) görsel açıdan iyi ama referans yok — Şiddet 2
**Konum:** Satır 160-188.
**Gözlem:** `multi_part_damages` orange kartında listeleniyor, `affected_parts` chip'leri var — iyi tasarım. Ama hangi **fotoğrafta** bu hasarın görüldüğü belirtilmiyor. 12 fotodan birinde "Sol kapı + ön çamurluk birlikte hasar" yazıyor ama hangi açıdan çekilmiş — bilinmiyor.
**Öneri:** Eğer backend `damage.source_image_index` döndürebilirse her hasarın altına mini thumbnail (clickable).

---

## 5. History / Geçmiş Sayfası (`/history`)

### Bulgu M5.1 — Thumbnail yokluğunda boş kamera ikonu, "bozuk" izlenimi (RAPORLANAN ŞİKAYET) — Şiddet 4
**Konum:** `app/history/page.tsx` satır 237-254.
**Gözlem:** `it.thumbnail_url` undefined olduğunda gri kart + sönük Camera icon (`h-10 w-10 text-slate-400`). Hiçbir yardım metni yok — "Bu inceleme bozuk mu, henüz yüklenmedi mi, silindi mi?" belirsiz.
12 foto yükleyen kullanıcı backend'in thumbnail üretmediğini görür → tüm geçmişi "kayıp" sanır.
**`MultiImageThumbnailGrid` paketinde `ThumbnailFallback` bileşeni VAR (brand-50 gradient + Görsel hazırlanıyor aria-label) — kullanılmıyor.**
**Öneri:**
- `ThumbnailFallback` kullan (brand renkleri + "Görsel hazırlanıyor" tooltip).
- Status `completed` ama thumbnail yoksa açıklama: "Görsel henüz hazır değil — birkaç saniye sonra yenile."
- Status `failed` ise farklı ikon (`AlertCircle`) + "Bu inceleme tamamlanmadı" footer.

### Bulgu M5.2 — `damage_count: 0` "Hasarsız" demek değil — Şiddet 3
**Konum:** Satır 264.
**Gözlem:** `t('damageCount', { count: it.damage_count })` = "0 hasar" yazıyor. Demo data'da bile `status: 'failed'` + `damage_count: 0` (satır 33-35) — failed inspection için "0 hasar" yazısı yanıltıcı. Liste seviyesinde `unassigned_damages` görünmüyor (sadece toplam aggregate).
**Öneri:**
- Status `completed && damage_count === 0` → "Hasar tespit edilmedi" (yeşil rozet)
- Status `completed && damage_count > 0` → "{n} hasar"
- Status `failed` → "Tamamlanmadı" (hasar sayısı gizle)
- Status `processing/queued` → "Hazırlanıyor…" (sayıyı gizle)

### Bulgu M5.3 — Status filtresi raw kod gösteriyor — Şiddet 3 (M1.M2/M3 ile çakışıyor)
**Konum:** Satır 161-165.
**Gözlem:** `<option value={s}>{s}</option>` — kullanıcı dropdown'da "queued / processing / completed / failed" görüyor. `useTranslations('status')` mevcut ama bağlanmamış.
**Öneri:** `<option value={s}>{tStatus(s)}</option>` (Kuyrukta / İşleniyor / Tamamlandı / Başarısız).

### Bulgu M5.4 — Filtrelerde hasar varlığı / maliyet aralığı eksik — Şiddet 2
**Konum:** Filter row (satır 127-200).
**Gözlem:** Sadece arama + status + tarih var. `tr.json`'da `filterDamageLevel` + `filterAllLevels` mevcut — UI'da bulunmuyor. 50+ inceleme tutan B2B kullanıcılar için "yalnızca hasarı olanları göster" kritik.
**Öneri:**
- `damage_present` toggle ("Yalnızca hasarlı")
- `severity` chipset (Hafif / Orta / Ağır)
- `cost_range` slider (0-25K TL)

### Bulgu M5.5 — Demo fallback ile gerçek veri ayrımı kaybolabilir — Şiddet 2
**Konum:** Satır 86-91.
**Gözlem:** Backend hata vermezse ama `items=[]` dönerse + filtre yoksa demo data gösteriliyor. Kullanıcı 12 foto yüklediği + sonuç gördüğü halde history boş gelirse demo'yu "gerçek geçmiş" sanabilir. `demoBanner` ancak `catch` bloğunda set ediliyor — happy-path boş listede banner yok.
**Öneri:** `usingDemo === true` her durumda amber banner gösterilsin (404 ile boş arasında ayrım net olsun).

---

## 6. Hata / Recovery

### Bulgu M6.1 — "Sunucuya ulaşılamıyor" + retry yok (results path) — Şiddet 4
**Konum:** `app/results/[id]/page.tsx` satır 59-61, ErrorBanner.
**Gözlem:** `error && status !== 'failed'` iken banner gösteriliyor — banner'da retry butonu yok. Kullanıcı yalnızca tarayıcı yenileme yapabilir (state kaybı + polling sayacı sıfırlanır).
`useInspectionPolling.retry()` döndürülüyor ama page bu fonksiyonu kullanmıyor.
**Öneri:** ErrorBanner'a "Tekrar kontrol et" butonu ekle → `retry()` çağırsın.

### Bulgu M6.2 — Polling exhausted (8 hata) sonrası kullanıcı kaybolur — Şiddet 3
**Konum:** Hook satır 184-196.
**Gözlem:** `paused=true` state set ediliyor ama UI bunu okumadığı için kullanıcı sadece son hata mesajını ("İnternet bağlantın yok") görür. "Inceleme sunucuda hâlâ devam ediyor" mesajı UI'a hiç ulaşmıyor.
**Öneri (M3.4 ile birlikte):** `paused` UI implement edildiğinde kullanıcı `/history` linkine yönlendirilsin.

### Bulgu M6.3 — Inspection ID kaybetme riski — Şiddet 2
**Konum:** Results sayfası tarayıcı kapanırsa.
**Gözlem:** Anonim kullanıcı 12 foto yüklediyse `inspection_id` URL'de + sessionStorage'da preview'da. Sekme kapanırsa preview kayıp (sessionStorage) + anonim demo'da history yok → kullanıcı işini tamamen kaybeder.
**Öneri:** Anonim akışta upload sonrası "Bu URL'i kaydet" hint'i + paylaşılabilir URL bilgisi.

### Bulgu M6.4 — 4xx hata kategorileri kullanıcıya aktarılmıyor — Şiddet 2
**Konum:** `lib/use-inspection-polling.ts` 401/403/404 fatal listesi.
**Gözlem:** 404 olduğunda kullanıcı "İnceleme bulunamadı" görür ama nedeni belirsiz (silindi mi? Yanlış mı yazdı?). Kullanıcı kendi inspection'ını bulamadığı sanrı yaşar.
**Öneri:** 404 için özel mesaj: "İnceleme bulunamadı — silinmiş veya bağlantı yanlış olabilir." + `/history` CTA.

---

## TOP 5 ÖNCELİKLİ İYİLEŞTİRMELER

### P1 — "Hasarsız" yanılgısını engelle (Bulgu M4.3) [Şiddet 5]
**Risk:** Kullanıcı 16 hasarı olan aracı "temiz" olarak okuyor → satım/sigorta kararında yanlış aksiyon, etik problem.
**Aksiyon:**
1. `result.parts` ile `unassigned_damages` ve `multi_part_damages` farkını UI'a yansıt.
2. "Hasarsız" verdicti yalnızca `allDamages.length === 0` iken görünsün.
3. Atanmamış hasar varsa header'da amber alert: "Hasar tespit edildi ama parça eşlemesi tamamlanamadı."
**Etki:** Güven ve ürün doğruluğu — MVP'nin temel değer önerisi.

### P2 — Polling hata mesajını düzelt: "İnternet yok" → "Sunucu yanıt vermiyor" (Bulgu M3.1 + M3.4) [Şiddet 5]
**Risk:** Backend tamamlanan inspection için kullanıcı "router'ım mı bozuk?" diye düşünür.
**Aksiyon:**
1. `navigator.onLine === false` testi ile gerçek offline'ı ayır.
2. `paused` state'ini UI'a bağla → "Tekrar kontrol et" butonu görünür olsun.
3. 5xx / timeout durumunda "Sonuç hazırlanıyor — birkaç dakika içinde Geçmiş'ten bakabilirsin" mesajı.
**Etki:** 12 foto yükleyip 60 sn bekleyen kullanıcılar.

### P3 — Multi-foto sonuç görselleştirmesi (Bulgu M4.1 + M4.4) [Şiddet 4]
**Risk:** 12 foto yüklenen sonuçta sadece 1 annotation görünüyor → "diğer fotoğraflar atıldı mı?" şüphesi.
**Aksiyon:**
1. `MultiImageThumbnailGrid` zaten paket içinde — results page'e bağla.
2. Her thumbnail'a hasar sayısı badge'i.
3. Tıklayınca o görselin annotation'ı ana viewport'a gelsin.
4. `getUploadedPreviews()` fallback'i (backend foto vermezse session storage preview).
**Etki:** "Tüm fotolarım işlendi" güveni + parça-foto eşleştirmesi keşfi.

### P4 — Anonim akışta upload progress bar (Bulgu M2.1) [Şiddet 4]
**Risk:** 12 × 5 MB upload sırasında 30-90 sn "donmuş" UI → abandonment.
**Aksiyon:**
1. `createInspection` çağrısına `onUploadProgress` callback wire et.
2. `tr.json` `inspect.progress.uploading` "({current}/{total})" formatını kullan.
3. Yüzde + dosya sayacı ("4/12 dosya, %33").
4. İptal butonu (AbortController).
**Etki:** Demo akışında ilk izlenim — auth versiyonu ile parite.

### P5 — History thumbnail fallback + status semantiği (Bulgu M5.1 + M5.2) [Şiddet 4]
**Risk:** Thumbnail yokken "bozuk inceleme" izlenimi + 0-hasar mesajının failed inspection'larda yanlış görünmesi.
**Aksiyon:**
1. `ThumbnailFallback` bileşenini (paketten) history cards'a uygula.
2. Status × damage_count matrix'i ile metni doğru göster:
   - completed + 0 hasar → yeşil "Hasar tespit edilmedi"
   - completed + n hasar → nötr "n hasar"
   - failed → "Tamamlanmadı"
   - queued/processing → "Hazırlanıyor…"
3. Status filtresinde `tStatus(s)` kullan (M5.3 fix).
**Etki:** Geri dönen kullanıcının ilk gördüğü ekran — retention.

---

## KOPYA ÖNERİLERİ (Türkçe Yeniden Yazım)

### Mode seçimi (Bulgu M1.1, M1.2)
| Eski | Yeni |
|---|---|
| modeAsync: "Kuyruğa al (önerilen)" | "Detaylı analiz (önerilen)" |
| modeAsyncDesc: "Arka planda işlenir. Çok sayıda görüntü için uygun." | "Tüm fotoğraflar incelenir. ~{seconds} sn'de hazır olur." |
| modeSync: "Anında işle" | "Hızlı önizleme" |
| modeSyncDesc: "Maks. 5 görüntü. Sonuç inline döner (~10-30 sn)." | "5 fotoğrafa kadar. Sonuç anında ekrana gelir." |

### Mode disable nedeni (yeni key)
> `inspect.modeSyncDisabled`: "Hızlı önizleme 5 fotoğrafa kadar — daha fazla foto için detaylı analiz gerekli."

### File counter (Bulgu M1.3)
| Eski | Yeni |
|---|---|
| filesSelected: "{count} dosya seçildi" | "{count} / {max} fotoğraf seçildi" |

### Upload progress (Bulgu M2.1, M2.4)
- Yüklerken: `inspect.progress.uploading` mevcut ("Fotoğraflar yükleniyor… ({current}/{total})") — sadece bağla.
- Yükleme bitti, redirect öncesi (yeni key):
  > `inspect.progress.handoff`: "Yükleme tamam — inceleme başlatılıyor…"

### Polling pending (Bulgu M3.2)
Rotasyon (her 5 sn):
- "Fotoğraflar sunucuya iletildi"
- "Araç parçaları algılanıyor…" (mevcut: `progress.detectingParts`)
- "Hasarlar tespit ediliyor…" (mevcut: `progress.detectingDamages`)
- "Maliyet hesaplanıyor…" (mevcut: `progress.calculatingCost`)
- "Neredeyse bitti…" (mevcut: `progress.almostDone`)

Gizle: `pollAttempts` (debug-only).

### Timeout (Bulgu M3.3) — yeni key'ler
| Key | Metin |
|---|---|
| `inspect.result.timeoutTitle` | "Sonuç hâlâ hazırlanıyor" |
| `inspect.result.timeoutDesc` | "İncelemen normalden uzun sürdü. Birkaç dakika sonra Geçmiş'ten bakabilir veya şimdi tekrar kontrol edebilirsin." |
| `inspect.result.goToHistory` | "Geçmişe git" |

### Paused (Bulgu M3.4) — mevcut anahtarları bağla
`inspect.result.pollPausedTitle` ("Sonuç hazırlanıyor") ve `pollPausedDesc` ("Sunucudan yanıt alınamadı. İnceleme arka planda hâlâ devam ediyor olabilir…") zaten yazılı — sadece UI'a bağla.

### Network error (Bulgu M3.1) — `errors.network.offline` parçala
| Eski | Yeni |
|---|---|
| `errors.network.offline`: "İnternet bağlantın yok" (her yerde) | Yalnızca `navigator.onLine === false` iken. |
| Yeni `errors.network.serverSlow`: | "Sunucu yanıt vermiyor — inceleme arka planda devam ediyor olabilir." |
| Yeni `errors.network.serverBlip`: | "Bağlantı dalgalandı — tekrar deneyelim." |

### Hasarsız verdict (Bulgu M4.3) — koşullu metin
| Senaryo | Metin |
|---|---|
| 0 hasar, 0 atanmamış | "Tebrikler, aracın temiz görünüyor." (mevcut `noDamageSubtitle`) |
| 0 parça hasarı, atanmamış var | YENİ: "Hasar belirtisi var ama parçaya tam atanamadı — manuel kontrol öneriyoruz." |
| Mixed | YENİ: "{damagedParts} hasarlı parça + {unassigned} parçaya atanamayan hasar" (mevcut `mixedResultTitle` zaten var, bağla) |

### Unassigned alert banner (Bulgu M4.2) — mevcut anahtarları bağla
`inspect.result.unassignedDamagesAlertTitle/Desc` zaten yazılı — header'a amber banner olarak göster (ratio > %30 iken).

### History card (Bulgu M5.1, M5.2) — yeni key'ler
| Key | Metin |
|---|---|
| `history.thumbnail.preparing` | "Görsel hazırlanıyor" |
| `history.damage.zero` | "Hasar tespit edilmedi" (yalnızca completed) |
| `history.damage.notCompleted` | "Tamamlanmadı" (failed için) |
| `history.damage.processing` | "Hazırlanıyor…" (queued/processing) |

### 404 mesajı (Bulgu M6.4)
| Eski | Yeni |
|---|---|
| `errors.http.404`: "Aradığın sayfa veya kayıt bulunamadı" | Inspection context'inde: "Bu inceleme bulunamadı — silinmiş veya bağlantı yanlış olabilir." (yeni key: `errors.inspectionNotFound`) |

### Anonim "URL'i kaydet" (Bulgu M6.3) — yeni key
> `inspect.anonymousSaveHint`: "Bu bağlantıyı kaydet — sonucuna daha sonra dönmek istersen kullanabilirsin."

---

## YOL HARİTASI ÖNERİSİ

**Sprint 1 (1 hafta) — Trust & Truth:**
- P1 (M4.3 hasarsız fix) + P2 (M3.1 network mesajı + M3.4 paused UI)
- Bu iki fix raporlanan tüm şikayetlerin temelini kapatır.

**Sprint 2 (1 hafta) — Multi-photo first class:**
- P3 (M4.1 thumbnail grid + M4.4 uploaded previews)
- P5 (M5.1 thumbnail fallback + M5.2 status semantiği)

**Sprint 3 (3-5 gün) — Polish:**
- P4 (M2.1 progress bar)
- M1.x mode UX iyileştirmeleri
- Kopya updates (i18n catalogue genişletme)

**Ölçüm önerisi:**
- Multi-foto inspection completion rate (12+ foto yükleyen kullanıcılarda)
- Results page bounce rate (60-180 sn pencereye düşen)
- History page click-through (results sayfasından gelen)
- "Hasarsız" verdictinin gerçek ground truth ile eşleşme oranı (manuel QA örneklemi)

---

**UX Researcher Notu:** Bu rapor statik koddan üretildi. Doğrulama için önerilenler:
1. 5 kullanıcı ile moderated test (12+ foto senaryosu)
2. Polling sırasında abandonment heatmap (Hotjar/PostHog)
3. "Hasarsız" verdict kararlarının manuel doğrulanması (50 inceleme örneklemi)
