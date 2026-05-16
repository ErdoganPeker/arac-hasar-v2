"""
download_data.py
Arac hasar tespiti MVP icin veri seti indirme orchestratoru.

Kullanim:
    python scripts/download_data.py --help
    python scripts/download_data.py --cardd-hf
    python scripts/download_data.py --carparts-ultra
    python scripts/download_data.py --roboflow-severity
    python scripts/download_data.py --cardd-manual C:/Downloads/CarDD_release.zip
    python scripts/download_data.py --all
    python scripts/download_data.py --all --dry-run

Notlar:
- Tum cikti yollari `services/ml/data/` altinda toplanir; mevcut
  `services/ml/prepare_data.py` ve `prepare_parts_data.py` ile uyumludur.
- CarDD ana set form basvurusu gerektirir (https://cardd-ustc.github.io).
  HF mirror (`harpreetsahota/CarDD`) form gerektirmez ama lisansi ayni
  (academic non-commercial). Ticari kullanim icin yazarlardan izin gerekir.
- Roboflow setleri icin ROBOFLOW_API_KEY environment variable veya .env
  dosyasinda tanimli olmali.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

# Proje koku (scripts/ klasorunun bir ust seviyesi)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ML_ROOT = PROJECT_ROOT / "services" / "ml"
DATA_ROOT = ML_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "scripts" / ".logs"

# Hedef alt klasorler (prepare_data.py / prepare_parts_data.py ile uyumlu)
CARDD_HF_DIR = DATA_ROOT / "cardd_hf"                # HuggingFace mirror
CARDD_RELEASE_DIR = DATA_ROOT / "CarDD_release"      # Manuel/form ana set
CARDD_YOLO_DIR = DATA_ROOT / "cardd_yolo"            # prepare_data.py ciktisi
PARTS_YOLO_DIR = DATA_ROOT / "parts_yolo"            # prepare_parts_data.py ciktisi
SEVERITY_ROBOFLOW_DIR = DATA_ROOT / "severity_roboflow"

# Disk gereksinim tahminleri (GB)
DISK_ESTIMATES_GB = {
    "cardd_hf": 6.5,
    "cardd_release": 6.5,
    "carparts_ultra": 1.2,
    "severity_roboflow": 0.5,
    "yolo_outputs": 7.0,  # prepare_data.py kopyalari da dahil
}


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

def setup_logger(name: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s",
                            datefmt="%H:%M:%S")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    logger.info("Log dosyasi: %s", log_file)
    return logger


# -----------------------------------------------------------------------------
# Yardimcilar
# -----------------------------------------------------------------------------

@dataclass
class DownloadPlan:
    name: str
    target: Path
    est_gb: float
    requires_auth: bool
    requires_manual: bool
    notes: str


def free_disk_gb(path: Path) -> float:
    """Belirtilen path icin bos disk alanini GB cinsinden dondurur."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(str(path))
        return usage.free / (1024 ** 3)
    except Exception:
        return -1.0


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(chunk), b""):
            h.update(buf)
    return h.hexdigest()


def write_hash_sidecar(path: Path, logger: logging.Logger) -> str:
    """Bir dosyanin SHA256'sini hesaplayip yanina .sha256 olarak yazar."""
    digest = sha256_file(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    logger.info("SHA256 %s = %s", path.name, digest)
    return digest


def verify_hash(path: Path, expected: Optional[str], logger: logging.Logger) -> bool:
    if not expected:
        return True
    actual = sha256_file(path)
    ok = actual.lower() == expected.lower()
    if ok:
        logger.info("Hash dogrulandi: %s", path.name)
    else:
        logger.error("Hash UYUSMUYOR: %s\n  beklenen: %s\n  bulunan : %s",
                     path.name, expected, actual)
    return ok


def load_dotenv_if_present() -> None:
    """Basit .env loader (python-dotenv olmadan)."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def confirm_disk(target: Path, need_gb: float, logger: logging.Logger,
                 dry_run: bool) -> bool:
    free = free_disk_gb(target)
    logger.info("Hedef: %s | Gereken ~%.1f GB | Bos: %.1f GB", target, need_gb, free)
    if free < 0:
        logger.warning("Disk alani okunamadi, devam ediliyor.")
        return True
    if free < need_gb * 1.2:
        logger.error("Yetersiz disk alani (%.1f < %.1f * 1.2).", free, need_gb)
        return False
    if dry_run:
        logger.info("[DRY-RUN] %s indirilecek (~%.1f GB)", target, need_gb)
    return True


# -----------------------------------------------------------------------------
# 1) CarDD - HuggingFace mirror
# -----------------------------------------------------------------------------

def download_cardd_hf(logger: logging.Logger, dry_run: bool = False) -> Optional[Path]:
    """harpreetsahota/CarDD setini HF Hub'dan indirir.

    Strateji:
      a) huggingface_hub.snapshot_download (resume destekli, yeniden calistirilabilir)
      b) datasets.load_dataset fallback
    """
    target = CARDD_HF_DIR
    if not confirm_disk(target, DISK_ESTIMATES_GB["cardd_hf"], logger, dry_run):
        return None
    if dry_run:
        logger.info("[DRY-RUN] HF repo: harpreetsahota/CarDD -> %s", target)
        return target

    target.mkdir(parents=True, exist_ok=True)

    repo_id = "harpreetsahota/CarDD"
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        logger.error("huggingface_hub yok. Kur: pip install -r scripts/requirements.txt")
        return None

    logger.info("HF snapshot baslat: %s -> %s", repo_id, target)
    try:
        path = snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            local_dir=str(target),
            local_dir_use_symlinks=False,  # Windows uyumu icin kopya
            resume_download=True,
        )
        logger.info("Tamamlandi: %s", path)
        return Path(path)
    except Exception as e:
        logger.warning("snapshot_download basarisiz: %s", e)
        logger.info("Fallback: datasets.load_dataset deneniyor...")
        try:
            from datasets import load_dataset
            ds = load_dataset(repo_id, cache_dir=str(target / ".hf_cache"))
            logger.info("datasets ile yuklendi: %s", list(ds.keys()))
            return target
        except Exception as e2:
            logger.error("HF indirme basarisiz: %s", e2)
            logger.error("Manuel: https://huggingface.co/datasets/%s", repo_id)
            return None


# -----------------------------------------------------------------------------
# 2) Ultralytics CarParts-Seg
# -----------------------------------------------------------------------------

def trigger_carparts_ultra(logger: logging.Logger, dry_run: bool = False) -> Optional[Path]:
    """Ultralytics CarParts-Seg veri setini ON-CACHE eder.

    Ultralytics datasets klasorune kendi indirir. Biz sadece pre-fetch tetikliyoruz.
    Kullanici sonrasinda:
        python services/ml/prepare_parts_data.py --use_ultralytics \\
            --output_dir services/ml/data/parts_yolo
    """
    if dry_run:
        logger.info("[DRY-RUN] Ultralytics 'carparts-seg.yaml' auto-download tetiklenecek")
        logger.info("[DRY-RUN] Tahmini boyut: ~%.1f GB", DISK_ESTIMATES_GB["carparts_ultra"])
        return None

    try:
        from ultralytics import YOLO
        from ultralytics.utils import SETTINGS
    except ImportError:
        logger.error("ultralytics yok. Kur: pip install ultralytics")
        return None

    datasets_dir = Path(SETTINGS.get("datasets_dir", "."))
    target = datasets_dir / "carparts-seg"
    logger.info("Ultralytics datasets_dir: %s", datasets_dir)
    logger.info("Hedef: %s", target)

    if not confirm_disk(datasets_dir, DISK_ESTIMATES_GB["carparts_ultra"], logger, False):
        return None

    if target.exists() and any(target.iterdir()):
        logger.info("Mevcut, atlandi: %s", target)
    else:
        logger.info("CarParts-Seg indirme tetikleniyor (CPU val on minimal config)...")
        try:
            m = YOLO("yolo11n-seg.pt")  # backbone auto-iner; Ultralytics dataset ZIP indirir
            try:
                m.val(data="carparts-seg.yaml", batch=1, device="cpu",
                      workers=0, verbose=False)
            except Exception as ve:
                # Indirme tetiklemek icin val'a guveniyoruz; val hatasi onemsiz
                logger.info("val tetikleyici tamamlandi (hata bekleniyordu): %s",
                            type(ve).__name__)
        except Exception as e:
            logger.error("Ultralytics indirme basarisiz: %s", e)
            logger.error("Manuel: https://docs.ultralytics.com/datasets/segment/carparts-seg/")
            return None

    logger.info("\nSonraki adim:\n  python services/ml/prepare_parts_data.py "
                "--use_ultralytics --output_dir %s", PARTS_YOLO_DIR)
    return target


# -----------------------------------------------------------------------------
# 3) Roboflow severity dataset
# -----------------------------------------------------------------------------

def download_roboflow_severity(logger: logging.Logger,
                               workspace: str = "car-damage-detection-cardd",
                               project: str = "car-damage-severity",
                               version: int = 1,
                               fmt: str = "yolov8",
                               dry_run: bool = False) -> Optional[Path]:
    """Roboflow Universe'den severity (minor/moderate/severe) seti indirir.

    NOT: workspace/project/version isimleri Roboflow Universe arama ile
    DOGRULANMALIDIR. Kullanici kendi se?tigi seti vermeli.
    """
    target = SEVERITY_ROBOFLOW_DIR
    if not confirm_disk(target, DISK_ESTIMATES_GB["severity_roboflow"], logger, dry_run):
        return None

    load_dotenv_if_present()
    api_key = os.environ.get("ROBOFLOW_API_KEY")

    if dry_run:
        logger.info("[DRY-RUN] Roboflow: %s/%s v%d -> %s",
                    workspace, project, version, target)
        logger.info("[DRY-RUN] API key durumu: %s",
                    "MEVCUT" if api_key else "EKSIK")
        return target

    if not api_key:
        logger.error("ROBOFLOW_API_KEY tanimli degil.")
        logger.error("Cozum:")
        logger.error("  1) https://app.roboflow.com/settings/api adresinden key al")
        logger.error("  2) %s\\.env dosyasina ekle:", PROJECT_ROOT)
        logger.error("       ROBOFLOW_API_KEY=xxxxxxxxxxxxxxxx")
        logger.error("  3) Veya manuel indir:")
        logger.error("     https://universe.roboflow.com -> 'car damage severity' arat")
        logger.error("     -> Download Dataset -> YOLOv8 format -> %s altina ac", target)
        return None

    try:
        from roboflow import Roboflow
    except ImportError:
        logger.error("roboflow yok. Kur: pip install -r scripts/requirements.txt")
        return None

    target.mkdir(parents=True, exist_ok=True)
    logger.info("Roboflow indirme: %s/%s v%d (format=%s)",
                workspace, project, version, fmt)
    try:
        rf = Roboflow(api_key=api_key)
        proj = rf.workspace(workspace).project(project)
        ver = proj.version(version)
        # Roboflow paketi indirme yapip path dondurur
        ds = ver.download(fmt, location=str(target))
        logger.info("Indirildi: %s", ds.location)
        return Path(ds.location)
    except Exception as e:
        logger.error("Roboflow indirme basarisiz: %s", e)
        logger.error("Manuel alternatif: Roboflow Universe arayuzunden ZIP indir,")
        logger.error("  %s altina cikart, prepare benzeri scripte yonlendir.", target)
        return None


# -----------------------------------------------------------------------------
# 4) CarDD manuel (form sonrasi ZIP)
# -----------------------------------------------------------------------------

def install_cardd_manual(zip_or_dir: Path, logger: logging.Logger,
                         dry_run: bool = False) -> Optional[Path]:
    """Kullanicinin form sonrasi indirdigi CarDD_release ZIP/klasorunu yerlestirir.

    Kabul edilen kaynaklar:
      - .zip dosyasi (icinde CarDD_release/ veya CarDD_COCO/)
      - Acilmis dizin (CarDD_release/ veya direkt CarDD_COCO/)
    """
    src = Path(zip_or_dir).expanduser().resolve()
    target = CARDD_RELEASE_DIR
    target.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        logger.error("Kaynak bulunamadi: %s", src)
        return None

    if not confirm_disk(target, DISK_ESTIMATES_GB["cardd_release"], logger, dry_run):
        return None

    if dry_run:
        logger.info("[DRY-RUN] %s -> %s", src, target)
        return target

    if src.is_file() and src.suffix.lower() == ".zip":
        logger.info("ZIP cikartiliyor: %s -> %s", src, target)
        try:
            write_hash_sidecar(src, logger)
        except Exception as e:
            logger.warning("Hash hesaplanamadi: %s", e)

        with zipfile.ZipFile(src, "r") as zf:
            members = zf.namelist()
            logger.info("Icerik: %d dosya", len(members))
            zf.extractall(target)
    elif src.is_dir():
        logger.info("Dizin kopyalaniyor: %s -> %s", src, target)
        # Tum icerigi merge et
        for item in src.iterdir():
            dst = target / item.name
            if dst.exists():
                logger.info("  atlandi (var): %s", dst.name)
                continue
            if item.is_dir():
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)
    else:
        logger.error("Desteklenmeyen kaynak: %s", src)
        return None

    # CarDD_COCO klasorunu bul (iki seviye derinlik kontrol)
    candidates = list(target.glob("**/CarDD_COCO"))
    cardd_coco = candidates[0] if candidates else target / "CarDD_COCO"
    logger.info("CarDD_COCO yolu: %s (var: %s)", cardd_coco, cardd_coco.exists())

    logger.info("\nSonraki adim:\n  python services/ml/prepare_data.py "
                "\\\n    --cardd_root %s \\\n    --output_dir %s",
                cardd_coco, CARDD_YOLO_DIR)
    return cardd_coco


# -----------------------------------------------------------------------------
# Planning / dry-run raporu
# -----------------------------------------------------------------------------

def build_plans(args: argparse.Namespace) -> Iterable[DownloadPlan]:
    plans = []
    if args.cardd_hf or args.all:
        plans.append(DownloadPlan(
            "CarDD (HuggingFace mirror)",
            CARDD_HF_DIR,
            DISK_ESTIMATES_GB["cardd_hf"],
            requires_auth=False,
            requires_manual=False,
            notes="Pretrained-friendly, otomatik resume.",
        ))
    if args.carparts_ultra or args.all:
        plans.append(DownloadPlan(
            "Ultralytics CarParts-Seg",
            Path("<ultralytics datasets_dir>/carparts-seg"),
            DISK_ESTIMATES_GB["carparts_ultra"],
            requires_auth=False,
            requires_manual=False,
            notes="Ultralytics auto-download tetiklenir.",
        ))
    if args.roboflow_severity or args.all:
        plans.append(DownloadPlan(
            "Roboflow severity",
            SEVERITY_ROBOFLOW_DIR,
            DISK_ESTIMATES_GB["severity_roboflow"],
            requires_auth=True,
            requires_manual=False,
            notes="ROBOFLOW_API_KEY gerekli (.env).",
        ))
    if args.cardd_manual:
        plans.append(DownloadPlan(
            "CarDD (manuel form sonrasi)",
            CARDD_RELEASE_DIR,
            DISK_ESTIMATES_GB["cardd_release"],
            requires_auth=False,
            requires_manual=True,
            notes="https://cardd-ustc.github.io form basvurusu sonrasi.",
        ))
    elif args.all:
        plans.append(DownloadPlan(
            "CarDD (manuel form sonrasi)",
            CARDD_RELEASE_DIR,
            DISK_ESTIMATES_GB["cardd_release"],
            requires_auth=False,
            requires_manual=True,
            notes="--all otomatik indirmez; form bekliyor.",
        ))
    return plans


def print_plan_table(plans: Iterable[DownloadPlan], logger: logging.Logger) -> None:
    logger.info("=" * 78)
    logger.info("INDIRME PLANI")
    logger.info("=" * 78)
    total = 0.0
    for p in plans:
        flags = []
        if p.requires_auth:
            flags.append("AUTH")
        if p.requires_manual:
            flags.append("MANUEL")
        flag_str = ",".join(flags) if flags else "-"
        logger.info("- %-35s ~%5.1f GB  [%s]", p.name, p.est_gb, flag_str)
        logger.info("    hedef: %s", p.target)
        logger.info("    not  : %s", p.notes)
        total += p.est_gb
    logger.info("-" * 78)
    logger.info("Toplam tahmini: ~%.1f GB", total)
    logger.info("=" * 78)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Arac hasar tespiti MVP veri seti indirici. "
            "Tum ciktilar services/ml/data/ altina kaydedilir."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--cardd-hf", action="store_true",
                   help="HuggingFace harpreetsahota/CarDD setini indir")
    p.add_argument("--carparts-ultra", action="store_true",
                   help="Ultralytics CarParts-Seg setini pre-fetch et")
    p.add_argument("--roboflow-severity", action="store_true",
                   help="Roboflow severity (minor/moderate/severe) setini indir")
    p.add_argument("--cardd-manual", type=str, default=None, metavar="PATH",
                   help="Form sonrasi indirilen CarDD_release ZIP/klasor yolu")
    p.add_argument("--all", action="store_true",
                   help="Mumkun olan setlerin hepsini indir (manuel adimlar haric)")

    p.add_argument("--rf-workspace", default="car-damage-detection-cardd",
                   help="Roboflow workspace slug (DOGRULA)")
    p.add_argument("--rf-project", default="car-damage-severity",
                   help="Roboflow project slug (DOGRULA)")
    p.add_argument("--rf-version", type=int, default=1,
                   help="Roboflow version no")
    p.add_argument("--rf-format", default="yolov8",
                   help="Roboflow export format (yolov8/yolov11/coco)")

    p.add_argument("--dry-run", action="store_true",
                   help="Sadece plan/disk raporu; indirme yapma")
    return p


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not any([args.cardd_hf, args.carparts_ultra, args.roboflow_severity,
                args.cardd_manual, args.all]):
        parser.print_help()
        print("\nHIC SUBCOMMAND VERILMEDI. Ornek: --all --dry-run")
        return 2

    logger = setup_logger("download_data")
    logger.info("Proje koku: %s", PROJECT_ROOT)
    logger.info("Veri koku: %s", DATA_ROOT)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)

    plans = list(build_plans(args))
    print_plan_table(plans, logger)

    if args.dry_run:
        logger.info("[DRY-RUN] Hicbir indirme yapilmadi.")
        return 0

    rc = 0
    if args.cardd_hf or args.all:
        if download_cardd_hf(logger) is None:
            rc = max(rc, 1)

    if args.carparts_ultra or args.all:
        if trigger_carparts_ultra(logger) is None:
            rc = max(rc, 1)

    if args.roboflow_severity or args.all:
        if download_roboflow_severity(
                logger,
                workspace=args.rf_workspace,
                project=args.rf_project,
                version=args.rf_version,
                fmt=args.rf_format) is None:
            rc = max(rc, 1)

    if args.cardd_manual:
        if install_cardd_manual(Path(args.cardd_manual), logger) is None:
            rc = max(rc, 1)
    elif args.all:
        logger.info("")
        logger.info("MANUEL ADIM (CarDD ana set):")
        logger.info("  1) https://cardd-ustc.github.io adresinde forma basvur (1-2 gun).")
        logger.info("  2) ZIP gelince:")
        logger.info("       python scripts/download_data.py --cardd-manual <ZIP_YOLU>")
        logger.info("  3) Bu arada HF mirror'i kullanarak pretrained baselineu egit.")

    logger.info("Bitti. RC=%d", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
