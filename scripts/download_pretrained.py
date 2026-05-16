"""
download_pretrained.py
Pretrained model agirliklarini services/ml/weights/ altina indirir.

Kullanim:
    python scripts/download_pretrained.py --help
    python scripts/download_pretrained.py --yolo11
    python scripts/download_pretrained.py --yolo26
    python scripts/download_pretrained.py --cardd-finetuned
    python scripts/download_pretrained.py --all
    python scripts/download_pretrained.py --all --dry-run

Indirilenler:
- Ultralytics YOLO11-seg (n, s, m) ve YOLO26-seg (n, s, m) backbone weights.
  Ultralytics paketi public CDN'den auto-fetch eder; biz weights/ klasorune
  kopyalariz ki train scripti yerel olarak gorsun.
- (Varsa) CarDD uzerinde finetune edilmis weights. HuggingFace 'harpreetsahota'
  altinda fine-tuned bir checkpoint paylasildiysa cekilir; yoksa kullaniciya
  bildirip atlanir.

Notlar:
- RTX 5050 (8 GB VRAM, Blackwell) icin: training'de 's' ve 'm' boyutlari
  pratik. 'n' hizli iteration icin idealdir.
- PyTorch CUDA 12.8 wheel kurulumu burada YAPILMAZ; bkz. scripts/DATA_README.md.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ML_ROOT = PROJECT_ROOT / "services" / "ml"
WEIGHTS_DIR = ML_ROOT / "weights"
PRETRAINED_DIR = ML_ROOT / "pretrained"  # registry-managed slot (selectable from API)
LOG_DIR = PROJECT_ROOT / "scripts" / ".logs"


# Ultralytics tarafindan auto-fetch edilen public weights
# Boyut tahminleri MB
YOLO11_SEG_MODELS = {
    "yolo11n-seg.pt": 5.9,
    "yolo11s-seg.pt": 19.7,
    "yolo11m-seg.pt": 43.7,
}
YOLO26_SEG_MODELS = {
    # Not: YOLO26 isimlendirmesi Ultralytics surumune gore degisebilir.
    # Eger model bulunamazsa yolo11 fallback'i kullanilir.
    "yolo26n-seg.pt": 6.0,
    "yolo26s-seg.pt": 20.0,
    "yolo26m-seg.pt": 44.0,
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


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(chunk), b""):
            h.update(buf)
    return h.hexdigest()


def write_hash_sidecar(path: Path, logger: logging.Logger) -> str:
    digest = sha256_file(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    logger.info("SHA256 %s = %s", path.name, digest)
    return digest


# -----------------------------------------------------------------------------
# Ultralytics weights
# -----------------------------------------------------------------------------

def fetch_one_ultralytics(name: str, logger: logging.Logger,
                          dry_run: bool = False) -> Optional[Path]:
    """Tek bir Ultralytics weight dosyasini cek + weights/ altina kopyala."""
    dst = WEIGHTS_DIR / name
    if dst.exists():
        logger.info("Mevcut: %s", dst)
        return dst

    if dry_run:
        logger.info("[DRY-RUN] %s -> %s", name, dst)
        return dst

    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("ultralytics yok. Kur: pip install ultralytics")
        return None

    logger.info("Ultralytics: %s yukleniyor (auto-download)...", name)
    try:
        m = YOLO(name)  # Bu satir CDN'den iner ve cache'e koyar
    except Exception as e:
        logger.error("Indirme basarisiz (%s): %s", name, e)
        return None

    # Ultralytics cache yolunu bul
    ckpt_path = getattr(m, "ckpt_path", None) or getattr(m, "pt_path", None)
    if not ckpt_path or not Path(ckpt_path).exists():
        # Fallback: Ultralytics current dir'e indirebilir
        candidates = [Path.cwd() / name, Path.home() / ".cache" / "ultralytics" / name]
        for c in candidates:
            if c.exists():
                ckpt_path = str(c)
                break

    if not ckpt_path or not Path(ckpt_path).exists():
        logger.warning("Cache yolu bulunamadi, weights kopyalanamadi: %s", name)
        return None

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ckpt_path, dst)
    logger.info("Kopyalandi: %s -> %s", ckpt_path, dst)
    try:
        write_hash_sidecar(dst, logger)
    except Exception as e:
        logger.warning("Hash sidecar yazilamadi: %s", e)
    return dst


def fetch_yolo_family(family: dict, logger: logging.Logger,
                      dry_run: bool = False) -> int:
    failures = 0
    for name in family:
        if fetch_one_ultralytics(name, logger, dry_run) is None:
            failures += 1
    return failures


# -----------------------------------------------------------------------------
# CarDD finetuned (varsa)
# -----------------------------------------------------------------------------

def fetch_cardd_finetuned(logger: logging.Logger,
                          dry_run: bool = False) -> Optional[Path]:
    """harpreetsahota/CarDD reposunda finetuned weight varsa cek.

    HF dataset reponun kendisi annotations icerir; model checkpoint
    genelde ayri bir repoda olur. Bilinen aday repolari sirayla dene.
    """
    candidates = [
        # (repo_id, repo_type, dosya ipucu)
        ("harpreetsahota/CarDD", "dataset", "best.pt"),
        ("harpreetsahota/cardd-yolo", "model", "best.pt"),
    ]

    if dry_run:
        logger.info("[DRY-RUN] Aday repolar: %s", [c[0] for c in candidates])
        return None

    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError:
        logger.error("huggingface_hub yok. Kur: pip install huggingface_hub")
        return None

    api = HfApi()
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)

    for repo_id, repo_type, hint in candidates:
        try:
            files = api.list_repo_files(repo_id=repo_id, repo_type=repo_type)
        except Exception as e:
            logger.info("Atlandi %s: %s", repo_id, e)
            continue

        pt_files = [f for f in files if f.endswith(".pt")]
        if not pt_files:
            logger.info("%s repoda .pt bulunmadi", repo_id)
            continue

        # En iyi adayi sec
        choice = next((f for f in pt_files if hint in f), pt_files[0])
        logger.info("Indiriliyor: %s :: %s", repo_id, choice)
        try:
            local = hf_hub_download(
                repo_id=repo_id,
                filename=choice,
                repo_type=repo_type,
                local_dir=str(WEIGHTS_DIR),
                local_dir_use_symlinks=False,
            )
            dst = WEIGHTS_DIR / f"cardd_finetuned_{Path(choice).name}"
            shutil.copy2(local, dst)
            logger.info("Kaydedildi: %s", dst)
            try:
                write_hash_sidecar(dst, logger)
            except Exception as e:
                logger.warning("Hash sidecar yazilamadi: %s", e)
            return dst
        except Exception as e:
            logger.warning("Indirme hatasi (%s): %s", repo_id, e)

    logger.info("CarDD-finetuned weight bulunamadi. Pretrained backbone + "
                "kendi finetune'unuzla devam edebilirsiniz.")
    return None


# -----------------------------------------------------------------------------
# Roboflow Universe public projects (frontend model toggle)
# -----------------------------------------------------------------------------

def fetch_roboflow_registry(logger: logging.Logger,
                            dry_run: bool = False) -> int:
    """Pretrained registry'deki tum roboflow entry'leri indir.

    Tek tek `pretrained_registry.PretrainedEntry.roboflow` dict'ini okur ve
    Roboflow SDK ile YOLOv8 export'unu PRETRAINED_DIR/<entry.id>/ altina iner.

    Returns
    -------
    int  Basarisiz indirme sayisi.
    """
    api_key = os.getenv("ROBOFLOW_API_KEY")
    if not api_key:
        logger.warning("ROBOFLOW_API_KEY env yok — Roboflow indirmesi atlanir")
        return 0

    # Lazy import: registry sadece bu CLI'da gerekli.
    sys.path.insert(0, str(ML_ROOT))
    try:
        from pretrained_registry import get_registry  # type: ignore
    except Exception as e:
        logger.error("pretrained_registry import edilemedi: %s", e)
        return 1

    try:
        from roboflow import Roboflow  # type: ignore
    except ImportError:
        logger.error("roboflow paketi yok. Kur: pip install roboflow")
        return 1

    PRETRAINED_DIR.mkdir(parents=True, exist_ok=True)
    rf = Roboflow(api_key=api_key)
    failures = 0

    for entry in get_registry().all_entries():
        if entry.source != "roboflow" or not entry.roboflow:
            continue
        out_dir = PRETRAINED_DIR / entry.id
        if (out_dir / "weights" / "best.pt").exists():
            logger.info("Mevcut: %s", out_dir / "weights" / "best.pt")
            continue
        if dry_run:
            logger.info("[DRY-RUN] roboflow: %s -> %s", entry.id, out_dir)
            continue
        try:
            ws = entry.roboflow["workspace"]
            proj = entry.roboflow["project"]
            ver = int(entry.roboflow.get("version", 1))
            fmt = entry.roboflow.get("format", "yolov8")
            logger.info("Roboflow %s/%s v%d (%s)", ws, proj, ver, fmt)
            project = rf.workspace(ws).project(proj)
            dataset = project.version(ver).download(fmt, location=str(out_dir))
            logger.info("Indirildi: %s -> %s", entry.id, dataset.location)
        except Exception as e:  # noqa: BLE001
            logger.warning("Roboflow indirme hatasi (%s): %s", entry.id, e)
            failures += 1
    return failures


def fetch_ultralytics_for_registry(logger: logging.Logger,
                                   dry_run: bool = False) -> int:
    """Pretrained registry'deki ultralytics entry'leri PRETRAINED_DIR'a kopyala.

    Auto-fetch zaten ultralytics tarafindan yapilir; biz hedef dosyaya
    kopyalariz ki ModelManager onu bulsun.
    """
    sys.path.insert(0, str(ML_ROOT))
    try:
        from pretrained_registry import get_registry  # type: ignore
    except Exception as e:
        logger.error("pretrained_registry import edilemedi: %s", e)
        return 1

    PRETRAINED_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    for entry in get_registry().all_entries():
        if entry.source != "ultralytics":
            continue
        dst = entry.resolved_path()
        if dst.exists():
            logger.info("Mevcut: %s", dst)
            continue
        if dry_run:
            logger.info("[DRY-RUN] ultralytics: %s -> %s", entry.id, dst)
            continue
        # weights_path basename'i ultralytics standard adi (yolo11m-seg.pt)
        wname = Path(entry.weights_path).name if entry.weights_path else f"{entry.id}.pt"
        src = fetch_one_ultralytics(wname, logger, dry_run=False)
        if src is None or not Path(src).exists():
            failures += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        logger.info("Kopyalandi: %s -> %s", src, dst)
    return failures


# -----------------------------------------------------------------------------
# Planning
# -----------------------------------------------------------------------------

@dataclass
class WeightPlan:
    name: str
    size_mb: float


def print_plan(args: argparse.Namespace, logger: logging.Logger) -> None:
    items = []
    if args.yolo11 or args.all:
        items.extend(YOLO11_SEG_MODELS.items())
    if args.yolo26 or args.all:
        items.extend(YOLO26_SEG_MODELS.items())
    if args.cardd_finetuned or args.all:
        items.append(("cardd_finetuned_best.pt (varsa)", 50.0))

    logger.info("=" * 70)
    logger.info("PRETRAINED PLAN")
    logger.info("=" * 70)
    total = 0.0
    for n, s in items:
        logger.info("- %-35s ~%6.1f MB", n, s)
        total += s
    logger.info("-" * 70)
    logger.info("Toplam tahmini: ~%.1f MB", total)
    logger.info("Hedef: %s", WEIGHTS_DIR)
    logger.info("=" * 70)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pretrained YOLO weights indirici (services/ml/weights/)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--yolo11", action="store_true",
                   help="YOLO11-seg (n,s,m) backbone agirliklari")
    p.add_argument("--yolo26", action="store_true",
                   help="YOLO26-seg (n,s,m) backbone agirliklari (Ultralytics surumune bagli)")
    p.add_argument("--cardd-finetuned", action="store_true",
                   help="HuggingFace'te CarDD finetuned ckpt varsa cek")
    p.add_argument("--all", action="store_true",
                   help="Tumunu indir")
    p.add_argument("--registry", action="store_true",
                   help=(
                       "pretrained_registry.py icindeki ultralytics + roboflow "
                       "entry'leri services/ml/pretrained/ altina indir. Frontend "
                       "model toggle'inde gorunecekler."
                   ))
    p.add_argument("--dry-run", action="store_true",
                   help="Sadece plani goster")
    return p


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not any([args.yolo11, args.yolo26, args.cardd_finetuned, args.all, args.registry]):
        parser.print_help()
        print("\nHIC SUBCOMMAND VERILMEDI. Ornek: --all --dry-run veya --registry")
        return 2

    logger = setup_logger("download_pretrained")
    logger.info("Hedef weights/: %s", WEIGHTS_DIR)
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)

    print_plan(args, logger)

    if args.dry_run:
        logger.info("[DRY-RUN] Indirme yapilmadi.")
        return 0

    failures = 0
    if args.yolo11 or args.all:
        failures += fetch_yolo_family(YOLO11_SEG_MODELS, logger)
    if args.yolo26 or args.all:
        failures += fetch_yolo_family(YOLO26_SEG_MODELS, logger)
    if args.cardd_finetuned or args.all:
        fetch_cardd_finetuned(logger)  # Yoksa sessiz gec

    if args.registry or args.all:
        logger.info("--- Registry pretrained (frontend toggle) ---")
        failures += fetch_ultralytics_for_registry(logger, dry_run=False)
        failures += fetch_roboflow_registry(logger, dry_run=False)

    logger.info("Tamamlandi. Basarisiz: %d", failures)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
