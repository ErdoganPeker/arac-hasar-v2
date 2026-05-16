# Veri Hazirlik Rehberi — Arac Hasar Tespiti MVP

Bu rehber, `services/ml/` icin gereken tum veri setlerini ve pretrained
model agirliklarini nasil indirip dogrulayacaginizi anlatir.

## 0. Hizli Baslangic

```powershell
# 1) Bagimliliklar (sadece scriptler icin)
pip install -r scripts/requirements.txt

# 2) Plan/disk raporu (hicbir sey indirmez)
python scripts/download_data.py --all --dry-run
python scripts/download_pretrained.py --all --dry-run

# 3) Pretrained weights + CarDD HF mirror + CarParts-Seg (paralel)
python scripts/download_pretrained.py --yolo11
python scripts/download_data.py --cardd-hf
python scripts/download_data.py --carparts-ultra

# 4) Form dolduktan ve CarDD ZIP elinize ulastiginda:
python scripts/download_data.py --cardd-manual "C:\Users\Erdogan\Downloads\CarDD_release.zip"

# 5) Dogrulama
python scripts/verify_data.py
```

## 1. Veri Setleri

### 1.1. CarDD (Car Damage Detection)
- **Kaynak**: https://cardd-ustc.github.io
- **Yayin**: Wang et al., 2023. ~4000 goruntu, 6 sinif segmentation:
  dent, scratch, crack, glass_shatter, lamp_broken, tire_flat.
- **Lisans**: **Academic, non-commercial**. Ticari kullanim icin
  yazarlarla yazili izin gerekir. MVP demo/POC tamam, satis oncesi
  yeniden lisansla.
- **Erisim yolu A (resmi form, ~1-2 gun)**:
  Form gonderildikten sonra ZIP linki e-postaya gelir.
  ```powershell
  python scripts/download_data.py --cardd-manual "C:\path\to\CarDD_release.zip"
  ```
  Bu komut `services/ml/data/CarDD_release/` altina cikartir ve
  `services/ml/prepare_data.py` icin dogru yolu yazdirir.
- **Erisim yolu B (HF mirror, form bekleme yok)**:
  ```powershell
  python scripts/download_data.py --cardd-hf
  ```
  Hedef: `services/ml/data/cardd_hf/`. Lisans CarDD ile ayni — sadece
  data erisimi farkli.
- **Disk**: ~6.5 GB ham + ~7 GB YOLO dump (toplam ~14 GB icin yer ayirin).

### 1.2. Ultralytics CarParts-Seg (parca segmentasyonu)
- **Kaynak**: https://docs.ultralytics.com/datasets/segment/carparts-seg/
- **Boyut**: ~1.2 GB. 21 sinif (kapilar, tamponlar, farlar, ...).
- **Lisans**: Roboflow community license, ticari kullanima izinli.
- **Indirme**: Ultralytics otomatik halleder; biz tetikliyoruz:
  ```powershell
  python scripts/download_data.py --carparts-ultra
  python services/ml/prepare_parts_data.py --use_ultralytics ^
      --output_dir services/ml/data/parts_yolo
  ```

### 1.3. Roboflow severity (minor/moderate/severe)
- **Kaynak**: https://universe.roboflow.com (workspace/project kullanici secimi)
- **Erisim**: ROBOFLOW_API_KEY gerekli (`https://app.roboflow.com/settings/api`).
  Repo kokune `.env` ekleyin:
  ```
  ROBOFLOW_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  ```
- **Indirme**:
  ```powershell
  python scripts/download_data.py --roboflow-severity ^
      --rf-workspace car-damage-detection-cardd ^
      --rf-project car-damage-severity ^
      --rf-version 1
  ```
- **NOT**: Workspace/project slug'lari Roboflow Universe'de arayip
  DOGRULAYIN. Default degerler placeholder'dir.

## 2. Pretrained Agirliklar

```powershell
# YOLO11 ailesi (n, s, m) — onerilen baslangic
python scripts/download_pretrained.py --yolo11

# YOLO26 ailesi (Ultralytics surumune bagli; yoksa atlanir)
python scripts/download_pretrained.py --yolo26

# CarDD-finetuned ckpt (HF'te varsa)
python scripts/download_pretrained.py --cardd-finetuned
```

Hedef: `services/ml/weights/*.pt` + `.sha256` sidecar.

## 3. Sirayla Yapilacaklar

1. `pip install -r scripts/requirements.txt`
2. `python scripts/download_pretrained.py --yolo11` (2-3 dk)
3. `python scripts/download_data.py --cardd-hf` (10-60 dk, baglantiya bagli)
4. `python scripts/download_data.py --carparts-ultra` (5-10 dk)
5. Paralel olarak CarDD resmi forma basvur (https://cardd-ustc.github.io).
6. CarDD HF mirror'i ile `prepare_data.py` calistirip baseline egit.
7. Resmi ZIP gelince `--cardd-manual` ile guncelle, modeli yeniden egit.
8. `python scripts/verify_data.py` ile her adim sonrasi dogrula.

## 4. Donanim Onerileri — RTX 5050 (8 GB VRAM, Blackwell)

- **PyTorch CUDA 12.8 wheel**:
  ```powershell
  pip install --index-url https://download.pytorch.org/whl/cu128 ^
      torch torchvision torchaudio
  ```
- **VRAM butcesi**:
  - `yolo11n-seg` `imgsz=640` `batch=16` → ~3.5 GB
  - `yolo11s-seg` `imgsz=640` `batch=12` → ~5.5 GB
  - `yolo11m-seg` `imgsz=640` `batch=6`  → ~7.5 GB (mixed precision)
- **Disk**: SSD'de en az 30 GB bos alan (ham + YOLO dump + checkpoint'ler).
- **RAM**: 16 GB yeterli; 32 GB ile data loader prefetch rahatlar.
- **Worker**: `workers=4` Windows'ta genelde stabil. Hatada `workers=0`.

## 5. Sorun Giderme

| Sorun | Cozum |
|------|-------|
| `huggingface_hub.errors.HfHubHTTPError 401` | `huggingface-cli login` (CarDD HF mirror public, normalde gerekmez) |
| `ROBOFLOW_API_KEY tanimli degil` | `.env` ekle veya `set ROBOFLOW_API_KEY=...` |
| Ultralytics `carparts-seg` indirilmiyor | `ultralytics` paketini guncelle: `pip install -U ultralytics` |
| CarDD ZIP cok yavas iniyor | HF mirror'a (1.1.B) dus, sonra resmi setle guncellersin |
| `torch.cuda.is_available() == False` | cu128 wheel'i kur, NVIDIA suruculerini guncelle |
| Disk dolu | Once `--dry-run` ile plan al; gereksiz `cardd_yolo/` kopyalarini sil |

## 6. Lisans Ozeti

| Set | Lisans | MVP icin | Ticari icin |
|-----|--------|----------|-------------|
| CarDD | Academic non-commercial | OK (POC) | Yazardan yazili izin |
| CarParts-Seg | Roboflow community | OK | OK |
| Roboflow severity | Project'e gore degisir | Kontrol et | Kontrol et |
| YOLO11/26 weights | AGPL-3.0 | OK | Ticari icin Ultralytics Enterprise |

**Yasal not**: Ulusal mevzuat (KVKK) ve Ultralytics AGPL etkilesimi, satis
asamasinda hukuksal incelemeden gecirilmelidir.

## 7. Dosya Yapisinin Beklenen Hali

```
services/ml/
  data/
    cardd_hf/                 # HF mirror snapshot
    CarDD_release/            # Form sonrasi resmi ZIP ictigi
      CarDD_COCO/
        annotations/
          instances_train2017.json
          instances_val2017.json
          instances_test2017.json
        train2017/  val2017/  test2017/
    cardd_yolo/               # prepare_data.py ciktisi
      images/{train,val,test}/
      labels/{train,val,test}/
    parts_yolo/               # prepare_parts_data.py ciktisi
    severity_roboflow/        # Roboflow ZIP ictigi
  weights/
    yolo11n-seg.pt + .sha256
    yolo11s-seg.pt + .sha256
    ...
scripts/.logs/                # Tum indirme/dogrulama loglari
```
