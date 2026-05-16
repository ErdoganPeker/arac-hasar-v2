# @arac-hasar/desktop — Hasarİ Desktop (Tauri 2)

Native Windows / macOS / Linux desktop uygulaması. Backend FastAPI'ye HTTP üzerinden bağlanır, native file picker ve toplu klasör işleme sunar. `packages/ui` ile web ile aynı React component'leri paylaşır.

## Gereksinimler

- Node.js ≥ 20 (pnpm 9+)
- Rust toolchain (1.77+) — `rustup` ile kur
- Platform-spesifik build araçları:
  - **Windows:** Microsoft C++ Build Tools, WebView2 (Win11'de var)
  - **macOS:** Xcode Command Line Tools
  - **Linux:** `libwebkit2gtk-4.1-dev`, `libsoup-3.0-dev`, `librsvg2-dev`, vs.

Detaylı önkoşullar: <https://tauri.app/start/prerequisites/>

## İlk kurulum

```bash
# Repo kökünden
pnpm install

# Tauri ikonları gerekli (placeholder olarak boş bırakıldı):
#   apps/desktop/src-tauri/icons/{32x32.png, 128x128.png, 128x128@2x.png, icon.icns, icon.ico}
# Geçici çözüm:
pnpm --filter @arac-hasar/desktop exec tauri icon ./public/logo.png   # mevcut bir PNG ile
```

## Geliştirme

```bash
# Sadece web (Vite dev server, 1420 portu)
pnpm dev:desktop

# Tauri penceresi + Vite HMR
pnpm --filter @arac-hasar/desktop tauri:dev
```

`http://localhost:8000` üzerinde FastAPI backend çalıştığında uygulama otomatik bağlanır. URL/anahtar `Ayarlar` sayfasından değiştirilir.

## Production build

```bash
pnpm --filter @arac-hasar/desktop tauri:build
```

Çıktılar `src-tauri/target/release/bundle/` altında.

## Sayfalar

- `/` — Ana sayfa, sistem durumu
- `/inspect` — Yeni inceleme (drag-drop + native file picker)
- `/results/:id` — İnceleme sonucu (3 tab: genel/parçalar/hasarlar)
- `/batch` — Klasör seç → toplu işleme (MVP'de stub)
- `/history` — Geçmiş incelemeler
- `/settings` — Backend URL, API key, tema

## Mimari

Tauri 2 WebView içinde Vite tarafından servis edilen React app. UI component'leri `@arac-hasar/ui`, tipler `@arac-hasar/types`. Yerel disk erişimi (`pickImages`, `pickFolder`) Tauri dialog/fs plugin'leri üzerinden. Ayarlar Tauri Store plugin'inde disk-persistent (settings.json).
